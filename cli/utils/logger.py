import logging

def setup_logger():
    """Setup basic logging."""
    logging.basicConfig(level=logging.INFO, format='%(levelname)s: %(message)s')
    return logging.getLogger(__name__)