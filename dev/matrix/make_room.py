"""Log in as Dr. Hofer, create the 'PGK requests' room WITHOUT encryption and invite the bot."""
import asyncio
import sys

from nio import AsyncClient, RoomCreateError


async def main(password: str) -> None:
    client = AsyncClient("http://localhost:8008", "@lena.hofer:klinikum.example")
    await client.login(password)
    # List her rooms first so reruns reuse the room instead of creating more.
    await client.sync(timeout=3000, full_state=True)
    for room_id, room in client.rooms.items():
        if room.name == "PGK requests":
            print(room_id)
            await client.close()
            return
    resp = await client.room_create(name="PGK requests", invite=["@pgk-bot:klinikum.example"],
                                    is_direct=False)  # no m.room.encryption state: unencrypted
    if isinstance(resp, RoomCreateError):
        sys.exit(f"could not create room: {resp.message}")
    print(resp.room_id)
    await client.close()


asyncio.run(main(sys.argv[1]))
