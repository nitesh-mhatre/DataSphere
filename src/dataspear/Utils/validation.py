import enum 

POSIBLE_SUFFIX_FOR_INDEX_URL = (
    "NIFTY",
    "BANKNIFTY",
    "1",  # SENSEX
    "INDIAVIX",
    "NIFTYIT",
)

POSIBLE_TIME_INTERVALS = (1,3,5,15,30,60,1440)

class ConnectionType(enum.IntEnum):
    Live = 1
    History = 0


class IndexRequestParameters:
    def __init__(self, suffix=None, end_time=None, start_time=None, interval=None, data_range=None ,connction_type=None):
        self.suffix = suffix
        self.end_time = end_time
        self.start_time = start_time
        self.interval = interval
        self.data_range = data_range
        self.connction_type = connction_type
        self.validate()

    def validate(self):
        if self.suffix not in POSIBLE_SUFFIX_FOR_INDEX_URL:
            raise ValueError(f"Invalid suffix: {self.suffix}. Must be one of {POSIBLE_SUFFIX_FOR_INDEX_URL}")
        if self.connction_type not in ConnectionType:
            raise ValueError(f"Invalid connection type: {self.connction_type}. Must be one of {list(ConnectionType)}")

        if self.connction_type == ConnectionType.History:
            if not isinstance(self.end_time, int) or not isinstance(self.start_time, int):
                raise ValueError("End time and start time must be integers representing milliseconds since epoch.")
            if self.start_time >= self.end_time:
                raise ValueError("Start time must be less than end time.")

        if self.connction_type == ConnectionType.Live:
            if not isinstance(self.data_range, int):
                raise ValueError("For data range value must be an integer.")
        
        if not isinstance(self.interval, int) or self.interval not in POSIBLE_TIME_INTERVALS:
            raise ValueError(f"Invalid interval: {self.interval}. Must be one of {POSIBLE_TIME_INTERVALS}")

        






