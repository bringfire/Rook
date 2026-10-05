"""Owned local configuration: pending firm settings and bounded retained workers."""
import asyncio
from dataclasses import asdict
import json
import threading
import time
from pathlib import Path
from aiohttp import web
from .vertex_media_http import read_body, failure
from ...providers.vertex_auth import VertexStore, VertexAuthError, VertexMode
from ...providers.vertex_oauth import DesktopOAuthClient
from ...providers.vertex_backend import (
    connect_vertex_oauth, save_vertex_configuration, disconnect_vertex,
    connect_vertex_workforce, check_firm_sign_in, _managed_chirp_recycler,
)
from ...providers.vertex_entra import EntraSessionAdapter
from ...providers.vertex_workforce_contract import (
    ActivationTicket, WorkforceActiveRecord, FirmSignInCheckResult,
    parse_firm_settings, opaque,
)
from ...providers.vertex_workforce_store import VertexWorkforceStore

class VertexConfigurationHttp:
    def __init__(self, *, store=None, recycler=None, authorize=None, entra=None, retire=None, check_timeout=30):
        self.store = store or VertexStore.production()
        self.firm_store = VertexWorkforceStore(self.store)
        self.recycler, self.authorize = recycler, authorize
        self.entra = entra or EntraSessionAdapter()
        if retire is None:
            from ...chirp_manager import retire_after_workforce_commit
            retire = retire_after_workforce_commit
        self.retire = retire
        self.check_timeout = min(30, check_timeout)
        self.worker = None
        self.cancel = None

    def status(self):
        record = self.store.read()
        return {'configured':record is not None,'mode':record.mode.value if record else None,
            'project_id':record.project_id if record else '', 'video_location':record.region if record else '',
            'image_location':'global','video_available':record is not None and record.region=='us-central1'}

    @staticmethod
    def _summary(settings):
        return {'label':settings.label,'project_id':settings.project_id,'video_location':settings.region,
            'image_location':'global','workforce_pool_user_project':settings.workforce_pool_user_project,'quota_project_id':settings.quota_project_id}

    def firm_status(self):
        active = self.firm_store.snapshot_active()
        pending = self.firm_store.read_pending()
        firm = active if isinstance(active, WorkforceActiveRecord) else None
        return {'contract_version':2,'active':self._summary(firm.settings) if firm else None,
            'active_generation':firm.generation if firm else None,
            'retirement_pending':firm.chirp_retirement_pending if firm else False,
            'pending':self._summary(pending[0]) if pending else None,
            'pending_revision':pending[1].pending_revision if pending else None,
            'authorization_epoch':pending[1].authorization_epoch if pending else None,
            'legacy_mode':active.mode.value if active is not None and firm is None else None,
            'state':'restart_required' if firm and firm.chirp_retirement_pending else 'signed_in' if firm else 'sign_in_required' if pending else 'unconfigured'}

    def mutate(self, body, stopped, deadline):
        def check():
            if stopped.is_set():
                raise VertexAuthError('vertex_authorization_declined','Google configuration was cancelled.')
            if time.monotonic() >= deadline:
                raise VertexAuthError('vertex_token_issuance_timeout','Google configuration timed out.')
        check()
        operation = body['operation']
        if operation == 'import_firm':
            path=Path(body['settings_path'])
            if not path.is_absolute(): raise ValueError('absolute path required')
            with path.open('rb') as stream: raw=stream.read(65537)
            settings=parse_firm_settings(raw)
            check(); self.firm_store.import_pending(settings,deadline=deadline,cancel_check=check)
            return self.firm_status()
        if operation == 'prepare_firm_reconnect':
            self.firm_store.prepare_reconnect(body['authorization_generation'],deadline=deadline,cancel_check=check); return self.firm_status()
        if operation == 'discard_firm':
            self.firm_store.discard_pending(deadline=deadline,cancel_check=check); return self.firm_status()
        if operation == 'connect_firm':
            return connect_vertex_workforce(ActivationTicket(body['pending_revision'],body['authorization_epoch']),store=self.firm_store,entra=self.entra,cancel_check=check,retire=self.retire)
        if operation == 'check_firm_sign_in':
            return check_firm_sign_in(body['authorization_generation'],store=self.firm_store,entra=self.entra,deadline=deadline,cancel_check=check,retire=self.retire)
        if operation == 'connect':
            path=Path(body['client_config_path'])
            if not path.is_absolute(): raise ValueError('absolute path required')
            with path.open('rb') as stream: raw=stream.read(65537)
            if len(raw)>65536: raise ValueError('client file too large')
            value=json.loads(raw.decode('utf-8'))
            if not isinstance(value,dict) or 'web' in value: raise ValueError('desktop client required')
            installed=value['installed']
            client=DesktopOAuthClient(installed['client_id'],installed['client_secret'])
            check()
            return connect_vertex_oauth(client,body['project_id'],body['video_location'],store=self.store,recycler=self.recycler,authorize=self.authorize,cancel_check=check)
        if operation == 'save':
            prior=self.store.read()
            if prior is None: raise ValueError('sign in first')
            if prior.mode is VertexMode.WORKFORCE:
                raise VertexAuthError('vertex_firm_settings_reimport_required','Reimport firm settings and sign in deliberately to change the active firm connection.')
            return save_vertex_configuration(prior.mode,body['project_id'],body['video_location'],service_account_path=prior.service_account_path,store=self.store,recycler=self.recycler,cancel_check=check)
        return disconnect_vertex(store=self.store,recycler=self.recycler,cancel_check=check)

    def _settled(self, worker):
        if not worker.cancelled(): worker.exception()
        if self.worker is worker:
            self.worker=None; self.cancel=None

    def _check_result(self, expected, code):
        current=self.firm_store.snapshot_active()
        return asdict(FirmSignInCheckResult('service_unavailable',code,expected if current is not None else None))

    async def execute(self, body, disconnected):
        fields={'status':{'operation'},'disconnect':{'operation'},'save':{'operation','project_id','video_location'},
            'connect':{'operation','project_id','video_location','client_config_path'},'firm_status':{'operation'},
            'import_firm':{'operation','settings_path'},'discard_firm':{'operation'},
            'connect_firm':{'operation','pending_revision','authorization_epoch'},
            'check_firm_sign_in':{'operation','authorization_generation'},'prepare_firm_reconnect':{'operation','authorization_generation'}}
        operation=body.get('operation')
        if not isinstance(operation,str) or operation not in fields or set(body)!=fields[operation] or any(type(value) is not str or not value or len(value)>4096 for value in body.values()):
            return failure('vertex_internal_request_invalid','Invalid Google configuration request.',400)
        try:
            for name in ('pending_revision','authorization_epoch','authorization_generation'):
                if name in body: opaque(body[name])
            if operation in ('status','firm_status'):
                return web.json_response({'success':True,'data':self.status() if operation=='status' else self.firm_status()})
            if 'video_location' in body and body['video_location']!='us-central1':
                return failure('vertex_model_region_unsupported','Choose us-central1 explicitly to enable video. Existing text settings were preserved.',400)
            if self.worker is not None:
                if operation!='disconnect':
                    return failure('vertex_configuration_busy','A Google configuration change is already in progress.',409)
                self.cancel.set()
                await asyncio.to_thread(self.firm_store.disconnect_all)
                try: await asyncio.to_thread(self.recycler or _managed_chirp_recycler,None)
                except Exception: return failure('vertex_restart_required','Restart required: a previous managed process could not be retired.',409)
                return web.json_response({'success':True,'data':self.status()})
            stopped=threading.Event()
            deadline=time.monotonic()+(self.check_timeout if operation=='check_firm_sign_in' else 210)
            worker=asyncio.create_task(asyncio.to_thread(self.mutate,body,stopped,deadline))
            self.worker,self.cancel=worker,stopped
            worker.add_done_callback(self._settled)
            try:
                while not worker.done():
                    if disconnected(): raise asyncio.CancelledError
                    if time.monotonic()>=deadline:
                        stopped.set()
                        if operation=='check_firm_sign_in':
                            return web.json_response({'success':True,'data':self._check_result(body['authorization_generation'],'vertex_token_issuance_timeout')})
                        return failure('vertex_token_issuance_timeout','Google configuration timed out. Read local settings before retrying.',504)
                    await asyncio.sleep(min(.05,max(0,deadline-time.monotonic())))
                result=await asyncio.shield(worker)
                if stopped.is_set():
                    return failure('vertex_authorization_changed','Google configuration was cancelled or changed. Read local settings.',409)
                if isinstance(result,FirmSignInCheckResult):
                    current=self.firm_store.snapshot_active()
                    if result.state=='signed_in' and (current is None or current.generation!=body['authorization_generation'] or current.chirp_retirement_pending):
                        result=FirmSignInCheckResult('authorization_changed','vertex_authorization_changed',body['authorization_generation'] if current else None)
                    return web.json_response({'success':True,'data':asdict(result)})
                if isinstance(result,dict): return web.json_response({'success':True,'data':result})
                if result.success:
                    if operation=='connect_firm':
                        current=self.firm_store.snapshot_active()
                        if current is None or current.generation!=result.generation:
                            return failure('vertex_authorization_changed','Firm authorization changed. Read local settings.',409)
                    return web.json_response({'success':True,'data':self.firm_status() if operation=='connect_firm' else self.status()})
                codes={'vertex_authorization_declined','vertex_oauth_admin_blocked','vertex_restart_required','vertex_firm_sign_in_required','vertex_workforce_exchange_denied','vertex_authorization_changed','vertex_token_issuance_timeout','vertex_auth_dependency_missing','vertex_firm_settings_reimport_required'}
                code=result.code if result.code in codes else 'vertex_configuration_failed'
                return failure(code,'Google configuration was not completed. Read local settings; administrator configuration may be required.',409)
            finally:
                stopped.set()
                # Do not extend a timed-out caller by awaiting a retained thread.
                # The identity-checked callback alone releases its mutation slot.
        except asyncio.CancelledError: raise
        except VertexAuthError as error:
            code=error.code if error.code=='vertex_firm_settings_reimport_required' else 'vertex_configuration_failed'
            return failure(code,'Google configuration could not be completed. Read local settings.',409)
        except Exception:
            return failure('vertex_configuration_failed','Google configuration could not be completed. Check the local configuration file.',400)

    async def shutdown(self, app):
        if self.cancel is not None: self.cancel.set()
        # The retained callback observes settlement; shutdown does not grant a
        # stale worker extra time or allow it to restore authorization.


def register_vertex_configuration_routes(app,service=None):
    selected=service or VertexConfigurationHttp()
    async def configure(request):
        try:
            body=await read_body(request)
            return await selected.execute(body,lambda:request.transport is None or request.transport.is_closing())
        except (ValueError,TypeError,UnicodeError):
            return failure('vertex_internal_request_invalid','Invalid Google configuration request.',400)
    app.router.add_route('*','/internal/providers/vertex/configuration',configure)
    app.on_shutdown.append(selected.shutdown)
