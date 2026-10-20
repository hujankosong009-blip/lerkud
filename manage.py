#!/usr/bin/env python
import os
import sys
from config.env import load_env
load_env()
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'config.settings')
from django.core.management import execute_from_command_line
execute_from_command_line(sys.argv)
