# Licensed to the Apache Software Foundation (ASF) under one
# or more contributor license agreements.  See the NOTICE file
# distributed with this work for additional information
# regarding copyright ownership.  The ASF licenses this file
# to you under the Apache License, Version 2.0 (the
# "License"); you may not use this file except in compliance
# with the License.  You may obtain a copy of the License at
#
#   http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing,
# software distributed under the License is distributed on an
# "AS IS" BASIS, WITHOUT WARRANTIES OR CONDITIONS OF ANY
# KIND, either express or implied.  See the License for the
# specific language governing permissions and limitations
# under the License.

# This code is copied and modified from
# https://github.com/Martiusweb/asynctest/blob/4b1284d6bab1ae90a6e8d88b882413ebbb7e5dce/asynctest/helpers.py
#
# At the time of copying, no NOTICE file was distributed with this work, so
# none is reproduced here.

import asyncio


async def exhaust_callbacks(loop):
    """
    Run the loop until all ready callbacks are executed.
    The coroutine doesn't wait for callbacks scheduled in the future with
    :meth:`~asyncio.BaseEventLoop.call_at()` or
    :meth:`~asyncio.BaseEventLoop.call_later()`.
    :param loop: event loop
    """
    while loop._ready:
        await asyncio.sleep(0, loop=loop)
