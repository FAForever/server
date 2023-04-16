import asyncio


async def test_broadcast_shutdown(broadcast_service):
    await broadcast_service.shutdown()

    broadcast_service.server.write_broadcast.assert_called_once()


async def test_wait_report_dirties(broadcast_service):
    await asyncio.wait_for(
        broadcast_service.wait_report_dirtes(),
        timeout=1
    )
