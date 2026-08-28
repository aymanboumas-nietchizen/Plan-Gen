"""
conftest.py — pytest configuration for PLANFGEN

Adds the planfgen/ project root to sys.path so that
'from planfgen.core.xxx import ...' works regardless of how tests are invoked.
"""
import sys, os
sys.path.insert(0, os.path.dirname(__file__))
