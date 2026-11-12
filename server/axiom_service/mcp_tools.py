"""MCP transport: the tools of AxiomSpec/api/mcp-tools.json over the same service.

The tool list is short on purpose: every definition costs the agent context before it asks anything. Each
tool is one operation of the HTTP contract, with the same answer and the same response schema.
"""
import json

from jsonschema import Draft202012Validator
import mcp.types as types
from mcp.server.lowlevel import Server
from starlette.concurrency import run_in_threadpool

from .service import EDITION, PACKAGE, QueryError

RENAMED = dict(snapshot='digest')  # a tool names the release `snapshot`; the operation calls it `digest`


def definitions(mode):
    """The tools served in `mode`, each with its input schema and a self-contained output schema."""
    contract = json.loads((PACKAGE / 'api/openapi.json').read_text())['components']['schemas']
    listed = json.loads((PACKAGE / 'api/mcp-tools.json').read_text())['tools']

    def output(name):
        needed, pending = {}, [name]
        while pending:
            current = pending.pop()
            if current not in needed:
                needed[current] = contract[current]
                text = json.dumps(contract[current])
                pending += [part.split('"')[0] for part in text.split('#/components/schemas/')[1:]]
        local = json.loads(json.dumps(needed).replace('#/components/schemas/', '#/$defs/'))
        # MCP requires an output schema to be an object schema at its root, so the type is stated beside the reference.
        return {'type': 'object', '$ref': f'#/$defs/{name}', '$defs': local}

    return [dict(tool, output_schema=output(tool['output'])) for tool in listed if mode in tool['modes']]


def build(service):
    """An MCP server whose tools call `service`. Stateless: a call carries everything it needs."""
    tools = {tool['name']: tool for tool in definitions(service.mode)}

    async def list_tools(context, parameters):
        return types.ListToolsResult(tools=[
            types.Tool(name=tool['name'], description=tool['description'], input_schema=tool['input_schema'],
                       output_schema=tool['output_schema']) for tool in tools.values()])

    async def call_tool(context, parameters):
        def failed(code, message):
            return types.CallToolResult(content=[types.TextContent(type='text', text=f'{code}: {message}')], is_error=True)

        tool = tools.get(parameters.name)
        if tool is None:
            return failed('NOT_FOUND', f'No tool named {parameters.name}')
        arguments = parameters.arguments or {}
        problems = sorted(error.message[:200] for error in Draft202012Validator(tool['input_schema']).iter_errors(arguments))
        if problems:
            return failed('INVALID_PARAMETER', '; '.join(problems[:3]))
        named = {RENAMED.get(name, name): value for name, value in arguments.items()}
        try:
            result = await run_in_threadpool(service.call, tool['operation_id'], **named)
        except QueryError as error:
            return failed(error.code, str(error))
        except Exception:  # a defect of the service: the agent still receives an error it can read
            return failed('INTERNAL_ERROR', 'The service could not answer this request')
        return types.CallToolResult(content=[types.TextContent(type='text', text=json.dumps(result, ensure_ascii=False, separators=(',', ':')))],
                                    structured_content=result)

    return Server('axiomspec', version=EDITION,
                  instructions='Requirements of one release, by ID. Look an ID up before changing code that carries it.',
                  on_list_tools=list_tools, on_call_tool=call_tool)
