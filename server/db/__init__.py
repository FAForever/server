from aiomysql.sa import create_engine


class FAFDatabase:
    def __init__(self, loop):
        self._loop = loop
        self.engine = None

    async def connect(self, host='localhost', port=3306, user='root',
                      password='', db='faf_test', minsize=1, maxsize=1,
                      echo=True):
        if self.engine is not None:
            raise ValueError("DB is already connected!")

        self.engine = await create_engine(
            host=host,
            port=port,
            user=user,
            password=password,
            db=db,
            autocommit=True,
            loop=self._loop,
            minsize=minsize,
            maxsize=maxsize,
            echo=echo
        )

    async def close(self):
        if self.engine is None:
            return

        self.engine.close()
        await self.engine.wait_closed()
        self.engine = None
