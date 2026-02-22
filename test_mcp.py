import asyncio
from mcp import ClientSession
from mcp.client.sse import sse_client

async def main():
    print("Connecting to MCP server via SSE...")
    async with sse_client("http://127.0.0.1:8001/mcp/sse") as (read, write):
        async with ClientSession(read, write) as session:
            await session.initialize()
            
            print("\nListing available tools:")
            tools_response = await session.list_tools()
            for tool in tools_response.tools:
                print(f" - {tool.name}: {tool.description}")

            print("\nTesting 'get_doctor_availability' tool:")
            result = await session.call_tool("get_doctor_availability", arguments={})
            print(f"Result: {result.content}")

if __name__ == "__main__":
    asyncio.run(main())
