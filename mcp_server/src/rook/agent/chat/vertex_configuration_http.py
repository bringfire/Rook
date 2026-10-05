"""Owned local configuration only: no Prime protocol, credentials, or public MCP route."""
import asyncio
import json
import threading
from pathlib import Path
from aiohttp import web
from .vertex_media_http import read_body, failure
from ...providers.vertex_auth import VertexStore, VertexAuthError, VertexMode
from ...providers.vertex_oauth import DesktopOAuthClient
from ...providers.vertex_backend import connect_vertex_oauth, save_vertex_configuration, disconnect_vertex

class VertexConfigurationHttp:
    def __init__(self, *, store=None, recycler=None, authorize=None):
        self.store = store or VertexStore.production()
        self.recycler = recycler
        self.authorize = authorize
        self.worker = None
        self.cancel = None

    def status(self):
        record = self.store.read()
        return {
            'configured': record is not None,
            'mode': record.mode.value if record else None,
            'project_id': record.project_id if record else '',
            'video_location': record.region if record else '',
            'image_location': 'global',
            'video_available': record is not None and record.region == 'us-central1',
        }

    def mutate(self, body, stopped):
        def check():
            if stopped.is_set():
                raise VertexAuthError('vertex_authorization_declined', 'Google configuration was cancelled.')
        check()
        operation = body['operation']
        if operation == 'connect':
            path = Path(body['client_config_path'])
            # Only local desktop client metadata; never return the file's contents.
            if not path.is_absolute(): raise ValueError('absolute path required')
            with path.open('rb') as stream:
                raw = stream.read(65537)
            if len(raw) > 65536: raise ValueError('client file too large')
            value = json.loads(raw.decode('utf-8'))
            if not isinstance(value, dict) or 'web' in value: raise ValueError('desktop client required')
            installed = value['installed']
            client = DesktopOAuthClient(installed['client_id'], installed['client_secret'])
            check()
            return connect_vertex_oauth(client, body['project_id'], body['video_location'], store=self.store,
                recycler=self.recycler, authorize=self.authorize, cancel_check=check)
        if operation == 'save':
            prior = self.store.read()
            if prior is None: raise ValueError('sign in first')
            return save_vertex_configuration(prior.mode, body['project_id'], body['video_location'],
                service_account_path=prior.service_account_path, store=self.store, recycler=self.recycler, cancel_check=check)
        check()
        return disconnect_vertex(store=self.store, recycler=self.recycler, cancel_check=check)

    async def execute(self, body, disconnected):
        fields = {'status': {'operation'}, 'disconnect': {'operation'},
            'save': {'operation','project_id','video_location'},
            'connect': {'operation','project_id','video_location','client_config_path'}}
        operation = body.get('operation')
        if not isinstance(operation, str) or operation not in fields or set(body) != fields[operation]:
            return failure('vertex_internal_request_invalid','Invalid Google configuration request.',400)
        if any(type(value) is not str or not value or len(value) > 4096 for value in body.values()):
            return failure('vertex_internal_request_invalid','Invalid Google configuration request.',400)
        try:
            if operation == 'status': return web.json_response({'success':True,'data':self.status()})
            if 'video_location' in body and body['video_location'] != 'us-central1':
                return failure('vertex_model_region_unsupported','Choose us-central1 explicitly to enable video. Existing text settings were preserved.',400)
            if self.worker is not None:
                return failure('vertex_configuration_busy','A Google configuration change is already in progress.',409)
            stopped = threading.Event()
            self.cancel = stopped
            self.worker = asyncio.create_task(asyncio.to_thread(self.mutate, body, stopped))
            try:
                while not self.worker.done():
                    if disconnected():
                        stopped.set()
                        raise asyncio.CancelledError
                    await asyncio.sleep(0.05)
                result = await self.worker
                if result.success:
                    return web.json_response({'success':True,'data':self.status()})
                # Never propagate exception or Google response text to the UI.
                code = result.code if result.code in {'vertex_authorization_declined','vertex_oauth_admin_blocked','vertex_restart_required'} else 'vertex_configuration_failed'
                return failure(code,'Google configuration was not completed. Previous settings may still apply; refresh local status.',409)
            finally:
                stopped.set()
                # Keep the mutation slot occupied until the worker actually settles.
                try: await asyncio.shield(self.worker)
                except Exception: pass
                self.worker = None
                self.cancel = None
        except asyncio.CancelledError: raise
        except Exception:
            return failure('vertex_configuration_failed','Google configuration could not be completed. Check the desktop client file and project settings.',400)

    async def shutdown(self, app):
        if self.cancel is not None: self.cancel.set()
        if self.worker is not None:
            try: await asyncio.shield(self.worker)
            except Exception: pass

def register_vertex_configuration_routes(app, service=None):
    selected = service or VertexConfigurationHttp()
    async def configure(request):
        try:
            body = await read_body(request)
            return await selected.execute(body, lambda: request.transport is None or request.transport.is_closing())
        except (ValueError, TypeError, UnicodeError):
            return failure('vertex_internal_request_invalid','Invalid Google configuration request.',400)
    app.router.add_route('*','/internal/providers/vertex/configuration',configure)
    app.on_shutdown.append(selected.shutdown)
