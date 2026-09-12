// SPDX-License-Identifier: Apache-2.0
// Exercise the installed host APIs against the real local Hyphae daemon.
import assert from "node:assert/strict";
import { execFileSync } from "node:child_process";
import { mkdtempSync, copyFileSync, writeFileSync, symlinkSync, readFileSync } from "node:fs";
import { tmpdir, homedir } from "node:os";
import { join } from "node:path";
import { pathToFileURL } from "node:url";
import { createBashTool, discoverAndLoadExtensions, ExtensionRunner, SessionManager, ModelRuntime, ModelRegistry } from "@earendil-works/pi-coding-agent";

const cwd = process.argv[2];
process.chdir(cwd);
const binary = "/runtime/hyphae";
const ui = (operation, args={}) => {
  const value = JSON.parse(execFileSync(binary,["agent","ui"], {input:JSON.stringify({schema:"hyphae-omarchy-control-v1",operation,arguments:args}),encoding:"utf8"}));
  assert.equal(value.ok,true,JSON.stringify(value));
  return value.result;
};
const piPath = join(homedir(),".pi/agent/extensions/hyphae-memory.ts");
const ocPath = join(process.env.XDG_CONFIG_HOME,"opencode/plugins/hyphae-memory.ts");
const types = mkdtempSync(join(tmpdir(),"hyo-types-"));
writeFileSync(join(types,"package.json"),'{"type":"module"}');
symlinkSync("/hosts/node_modules",join(types,"node_modules"));
for (const [source,name] of [[piPath,"pi.ts"],[ocPath,"opencode.ts"]]) copyFileSync(source,join(types,name));
execFileSync("node",["/hosts/node_modules/typescript/bin/tsc","--noEmit","--strict","--skipLibCheck","--target","ES2022","--module","NodeNext","--moduleResolution","NodeNext",join(types,"pi.ts"),join(types,"opencode.ts")],{stdio:"inherit"});

const loaded = await discoverAndLoadExtensions([],cwd,join(homedir(),".pi/agent"));
assert.deepEqual(loaded.errors,[]);
assert.equal(loaded.extensions.length,1);
const sessions = SessionManager.inMemory(cwd);
const models = await ModelRuntime.create({allowModelNetwork:false,refreshOnCreate:false,modelsPath:null,authPath:join(types,"auth.json"),modelsStorePath:join(types,"models.json")});
const runner = new ExtensionRunner(loaded.extensions,loaded.runtime,cwd,sessions,new ModelRegistry(models));
const errors=[];
runner.onError(error => errors.push(error));
const start = await runner.emitBeforeAgentStart("nebula shared host context",undefined,"Current system instructions",{});
assert.equal(start?.messages?.length,1,JSON.stringify({start,errors}));
assert.equal(start.systemPrompt,undefined);
assert.ok(start.messages[0].content.includes("nebula"));
assert.ok(Buffer.byteLength(start.messages[0].content) <= 2000);
const tools = runner.getAllRegisteredTools();
assert.equal(tools.length,5);
const recall = runner.getToolDefinition("hyphae_memory_recall");
let recalled;
try {
  recalled = await recall.execute("qa-recall",{query:"nebula"},undefined,undefined,runner.createContext());
} catch (error) {
  const config = JSON.parse(readFileSync(join(process.env.XDG_CONFIG_HOME,"hyphae/pi-agent-memory.json"),"utf8"));
  const input = [
    {jsonrpc:"2.0",id:1,method:"initialize",params:{protocolVersion:"2025-06-18",capabilities:{},clientInfo:{name:"conformance",version:"1"}}},
    {jsonrpc:"2.0",method:"notifications/initialized",params:{}},
    {jsonrpc:"2.0",id:2,method:"tools/call",params:{name:"hyphae_memory_recall",arguments:{query:"nebula"}}},
  ].map(JSON.stringify).join("\n")+"\n";
  const output = execFileSync(binary,["mcp","--profile","memory","--allow-write","--endpoint",config.endpoint],{input,encoding:"utf8",env:{...process.env,HYPHAE_NATIVE_API_KEY_FILE:config.credential_file}});
  console.error(output);
  throw error;
}
assert.ok(recalled.details.memories.length > 0);
const cancelled = new AbortController(); cancelled.abort();
await assert.rejects(recall.execute("qa-cancel",{query:"nebula"},cancelled.signal,undefined,runner.createContext()),/cancelled/);

// Execute a real Pi Bash tool and dispatch its actual result through Pi's runner.
writeFileSync(join(cwd,"package.json"),JSON.stringify({scripts:{test:"node -e \"process.stdout.write('fixture passed')\""}}));
const bash = createBashTool(cwd);
const bashResult = await bash.execute("qa-npm",{command:"npm test"},undefined,undefined);
await runner.emitToolResult({type:"tool_result",toolName:"bash",toolCallId:"qa-npm",input:{command:"npm test"},content:bashResult.content,details:bashResult.details,isError:false});
execFileSync(binary,["agent","maintain"]);
assert.ok(ui("recall",{query:"npm test",kind:"command"}).memories.some(m => m.text === "Command: npm test"));
const hidden = "HIDDEN_REASONING_MUST_NOT_ENTER_MEMORY";
sessions.appendMessage({role:"assistant",content:[{type:"thinking",thinking:hidden},{type:"text",text:"Decision: amber validates the public lifecycle."}],provider:"test",model:"fixture",api:"test",usage:{input:0,output:0,cacheRead:0,cacheWrite:0,totalTokens:0,cost:{input:0,output:0,cacheRead:0,cacheWrite:0,total:0}},stopReason:"stop",timestamp:Date.now()});
await runner.emit({type:"agent_settled"});
execFileSync(binary,["agent","maintain"]);
assert.ok(ui("recall",{query:"amber public lifecycle"}).memories.length > 0);
assert.equal(ui("recall",{query:hidden}).memories.length,0);
assert.deepEqual(errors,[]);

const {HyphaeMemory} = await import(pathToFileURL(ocPath).href);
const oc = await HyphaeMemory({directory:cwd, client:{session:{messages:async()=>({data:[]})}}});
const config = {mcp:{independent:{type:"local",command:["/usr/bin/true"]}}};
await oc.config(config);
assert.deepEqual(config.mcp.independent.command,["/usr/bin/true"]);
assert.equal(config.mcp["hyphae-memory"].command[0],binary);
const message = {message:{id:"msg_fixture"},parts:[{type:"text",text:"nebula shared host context"}]};
await oc["chat.message"]({sessionID:"ses_fixture",model:{providerID:"test",modelID:"fixture"}},message);
assert.equal(message.parts.length,2);
assert.equal(message.parts[1].synthetic,true);
assert.equal(message.parts[1].messageID,"msg_fixture");
assert.ok(message.parts[1].text.includes("nebula"));
await oc["tool.execute.after"]({tool:"bash",args:{command:"npm run build"}},{metadata:{exit:1}});
execFileSync(binary,["agent","maintain"]);
assert.equal(ui("recall",{query:"npm run build",kind:"command"}).memories.some(m => m.text === "Command: npm run build"),false);
console.log(JSON.stringify({pi:"loader, prompt, bounded MCP, cancellation, Bash result, public capture",opencode:"types, MCP contribution, prompt injection, failed-command rejection"}));
