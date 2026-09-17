// Synthetic source-owner test; never imports the installed runtime or its store.
import assert from 'node:assert/strict';
import fs from 'node:fs';
import cp from 'node:child_process';
import net from 'node:net';
import tls from 'node:tls';
import {createRequire, syncBuiltinESMExports} from 'node:module';
import {join, resolve, dirname, basename} from 'node:path';
import {pathToFileURL} from 'node:url';

const root = process.env.ROOK_STORAGE_PRIME_SOURCE;
const directory = process.env.PRIME_AGENT_CODING_AGENT_DIR;
const require = createRequire(join(root, 'package.json'));
const execFileSync = cp.execFileSync;
const reports = [];
let phase = 'load';
let contacts = 0;
const block = () => { contacts++; throw Error('external_contact_forbidden'); };
for (const name of ['spawn','spawnSync','exec','execSync','execFile','execFileSync','fork']) cp[name] = block;
net.Socket.prototype.connect = block;
tls.connect = block;
globalThis.fetch = block;

function observe(path) {
    if (dirname(resolve(String(path))).toLowerCase() !== resolve(directory).toLowerCase()) return;
    const name = basename(String(path));
    if (!/^(auth|settings|models)\.json(?:\..*\.tmp)?$/.test(name)) return;
    // Independent Windows/.NET ACL oracle, bounded and metadata-only. This is
    // the sole allowed fixture child; no product writer is replaced.
    const ps = "$ErrorActionPreference='Stop';$a=Get-Acl -LiteralPath $env:ROOK_STORAGE_OBSERVE;" +
        "[pscustomobject]@{owner=$a.Owner;protected=$a.AreAccessRulesProtected;aces=@($a.Access|ForEach-Object{" +
        "[pscustomobject]@{sid=$_.IdentityReference.Translate([Security.Principal.SecurityIdentifier]).Value;" +
        "rights=[int]$_.FileSystemRights;type=[string]$_.AccessControlType;inherit=[string]$_.InheritanceFlags}})}|ConvertTo-Json -Depth 5 -Compress";
    const raw = execFileSync('C:/Program Files/PowerShell/7/pwsh.exe', ['-NoProfile','-NonInteractive','-Command',ps],
        {env:{...process.env,ROOK_STORAGE_OBSERVE:resolve(String(path))},timeout:5000,maxBuffer:16384,windowsHide:true,encoding:'utf8'});
    reports.push({phase,name,acl:JSON.parse(raw)});
}
for (const name of ['writeFileSync','chmodSync','renameSync']) {
    const original = fs[name];
    fs[name] = (...args) => {
        const value = original(...args);
        observe(name === 'renameSync' ? args[1] : args[0]);
        return value;
    };
}
syncBuiltinESMExports();
if (process.versions.bun) {
    // Bun does not synchronize patched default fs methods into later named
    // imports. Its test hook supplies the same pass-through observer to those
    // imports; actual filesystem writes and Prime owners still execute.
    const {mock} = await import('bun:test');
    mock.module('fs', () => ({...fs, default:fs}));
    mock.module('node:fs', () => ({...fs, default:fs}));
}
for (const name of ['@earendil-works/pi-ai','@earendil-works/pi-agent-core'])
    assert.ok(fs.realpathSync(require.resolve(name)).toLowerCase().startsWith(root.toLowerCase()));
const load = path => import(pathToFileURL(join(root,path)).href);
try {
    const {AuthStorage, FileAuthStorageBackend} = await load('packages/coding-agent/src/core/auth-storage.ts');
    const {SettingsManager} = await load('packages/coding-agent/src/core/settings-manager.ts');
    const {ModelRegistry} = await load('packages/coding-agent/src/core/model-registry.ts');
    const {registerOAuthProvider} = await import(pathToFileURL(require.resolve('@earendil-works/pi-ai/oauth')).href);
    const authPath = join(directory, 'auth.json');
    phase = 'sync-create';
    const backend = new FileAuthStorageBackend(authPath);
    backend.withLock(() => ({result:undefined,next:JSON.stringify({synthetic:{type:'api_key',key:'synthetic-a'}})}));
    phase = 'async-replace';
    await backend.withLockAsync(async () => ({result:undefined,next:JSON.stringify({synthetic:{type:'api_key',key:'synthetic-b'}})}));
    const auth = AuthStorage.create(authPath,{configurationPolicy:'rookchat'});
    assert.equal(await auth.getApiKey('synthetic'), 'synthetic-b');
    registerOAuthProvider({id:'fixture-refresh',name:'Synthetic',async login(){throw Error('login_forbidden');},
        async refreshToken(value){return {...value,access:'synthetic-refreshed',expires:Date.now()+60000};},
        getApiKey(value){return value.access;}});
    phase = 'expired-synthetic';
    auth.set('fixture-refresh',{type:'oauth',access:'synthetic-expired',refresh:'synthetic-refresh',expires:0});
    phase = 'oauth-refresh';
    assert.equal(await auth.getApiKey('fixture-refresh'),'synthetic-refreshed');
    assert.equal(await AuthStorage.create(authPath,{configurationPolicy:'rookchat'}).getApiKey('fixture-refresh'),'synthetic-refreshed');
    phase = 'settings-replace';
    const settings = SettingsManager.create(directory,directory,{allowProjectResources:false});
    settings.setDefaultModel('synthetic-model');
    await settings.flush();
    settings.assertConfigurationStorageReady();
    assert.equal(SettingsManager.create(directory,directory,{allowProjectResources:false}).getDefaultModel(),'synthetic-model');
    phase = 'models-replace';
    const registry = ModelRegistry.create(auth,join(directory,'models.json'),'rookchat');
    await registry.saveConfigurationEndpoint({provider:'ollama',baseUrl:'http://127.0.0.1:11434/v1',api:'openai-completions',
        authHeader:false,headers:{action:'keep'},models:[{id:'fixture',name:'Fixture',reasoning:false,input:['text'],contextWindow:4096,maxTokens:32}]});
    assert.equal(contacts,0);
    process.stdout.write(JSON.stringify({outcome:'passed',contacts,reports})+'\n');
} catch {
    process.stderr.write('synthetic_storage_fixture_failed:'+phase+'\n');
    process.exitCode=1;
}
