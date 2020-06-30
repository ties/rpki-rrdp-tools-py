import os
import pytest

from lxml import etree

from rrdp_tools.rrdp import validate


def test_validate_accepts_valid(test_data_dir):
    with open(os.path.join(test_data_dir, 'valid_snapshot.xml'), 'r') as rrdp_file:
        doc = etree.parse(rrdp_file)
        validate(doc)
        # Document is valid,

def test_validate_accepts_snapshot(test_data_dir):
    with open(os.path.join(test_data_dir, 'sample_notification.xml'), 'r') as rrdp_file:
        doc = etree.parse(rrdp_file)
        validate(doc)
