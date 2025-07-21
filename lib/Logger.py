
import logging
import datetime
from logging.handlers import TimedRotatingFileHandler

class Logger:

    @classmethod
    def init(self):
        logger = logging.getLogger("run")
        if not logger.handlers:
            formatter = logging.Formatter('%(asctime)s - %(classname)s::%(funcName)s - %(levelname)s - %(message)s')
            handler = TimedRotatingFileHandler('logs/run.log', when='midnight',
                atTime=datetime.time(hour=18, minute=0))
            handler.setFormatter(formatter)
            logger.addHandler(handler)
