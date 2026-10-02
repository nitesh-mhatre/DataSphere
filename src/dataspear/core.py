import time

from dataspear.utils.validation import IndexRequestParameters, ConnectionType
from dataspear.utils.request_handler import RequestHandler


class DataConnection:
    def __init__(self, params: IndexRequestParameters = None):
        self.params = params
        self.request_handler = RequestHandler()

    async def fetch(self, start_time=None, end_time=None):
        if self.params is None:
            raise ValueError(
                "Parameters (`self.params`) must be set before calling fetch()."
            )

        if self.params.connection_type == ConnectionType.Live:
            current_ms = int(time.time() * 1000)
            self.params.start_time = current_ms - (self.params.data_range * 60 * 1000)
            self.params.end_time = current_ms
        else:
            # Only override the configured history range when explicitly passed.
            if start_time is not None:
                self.params.start_time = start_time
            if end_time is not None:
                self.params.end_time = end_time

        self.params.validate()
        error, response = await self.request_handler.fetch(self.params)
        if error:
            raise Exception(f"Error fetching data: {error}")
        return response


class IndexDataConnection(DataConnection):
    def __init__(
        self,
        suffix=None,
        end_time=None,
        start_time=None,
        interval=5,
        data_range=60,
        connection_type=ConnectionType.Live,
    ):
        params = IndexRequestParameters(
            suffix=suffix,
            end_time=end_time,
            start_time=start_time,
            interval=interval,
            data_range=data_range,
            connection_type=connection_type,
        )
        super().__init__(params=params)
