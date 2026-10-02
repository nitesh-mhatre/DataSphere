from dataspear.utils.validation import IndexRequestParameters, ConnectionType
from dataspear.utils.request_handler import RequestHandler
import time


class DataConnection:
    def __init__(self):
        self.params = None
        self.request_handler = RequestHandler()

    async def fetch(self, start_time = None, end_time= None):
        if self.params.connction_type == ConnectionType.Live:
            self.params.start_time = time.time() * 1000 - self.params.data_range * 60 * 1000
            self.params.end_time = time.time() * 1000
            self.params.validate()
        else:
            self.params.start_time = start_time
            self.params.end_time = end_time
            self.params.validate()

        await self.request_handler.fetch(self.params)

class IndexDataConnection(DataConnection):
    def __init__(self, suffix=None, end_time=None, start_time=None, interval=None, data_range=None ,connction_type=None):
        from dataspear.utils.validation import IndexRequestParameters
        self.params = IndexRequestParameters(suffix=suffix, end_time=end_time, start_time=start_time, 
                                             interval=interval, data_range=data_range, connction_type=connction_type)

    
