
async def test_broadcast_shutdown(broadcast_service):
    await broadcast_service.shutdown()

    broadcast_service.server.write_broadcast.assert_called_once()
