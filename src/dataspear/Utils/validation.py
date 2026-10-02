POSIBLE_SUFFIX_FOR_INDEX_URL = (
    "NIFTY",
    "BANKNIFTY",
    "1",  # SENSEX
    "INDIAVIX",
    "NIFTYIT",
)

POSIBLE_TIME_INTERVALS = (1,3,5,15,30,60,1440)



class IndexRequestParameters:
    def __init__(self, suffix, end_time, start_time, interval):
        self.suffix = suffix
        self.end_time = end_time
        self.start_time = start_time
        self.interval = interval
        self.validate()

    def validate(self):
        if self.suffix not in POSIBLE_SUFFIX_FOR_INDEX_URL:
            raise ValueError(f"Invalid suffix: {self.suffix}. Must be one of {POSIBLE_SUFFIX_FOR_INDEX_URL}")
        if not isinstance(self.end_time, int) or not isinstance(self.start_time, int):
            raise ValueError("End time and start time must be integers representing milliseconds since epoch.")
        if self.start_time >= self.end_time:
            raise ValueError("Start time must be less than end time.")
        if not isinstance(self.interval, int) or self.interval not in POSIBLE_TIME_INTERVALS:
            raise ValueError(f"Invalid interval: {self.interval}. Must be one of {POSIBLE_TIME_INTERVALS}")

        






