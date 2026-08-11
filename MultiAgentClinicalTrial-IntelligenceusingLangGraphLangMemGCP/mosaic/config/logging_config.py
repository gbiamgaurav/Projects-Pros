

# Central Logging Setup for Entire Project 

import logging 
import sys

def setup_logging(name: str) -> logging.Logger:
    """_summary_

    Args:
        name (str): _description_

    Returns:
        logging.Logger: _description_
    """
    logger = logging.getLogger(name) 
    if logger.handlers:
        return logger

    logger.setLevel(logging.INFO)
    handler = logging.StreamHandler(sys.stdout)

    formatter = logging.Formatter(
        fmt="%(asctime)s | %(levelname)-8s | %(name)s | %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",        
    )

    handler.setFormatter(formatter)
    logger.addHandler(handler)

    logger.propagate = False
    return logger
