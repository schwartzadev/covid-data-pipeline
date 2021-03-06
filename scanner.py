"""
scanner

scan the COVID-19 government sites
data is fetched and cleaned then pushed to a git repo
files are only updated if the cleaned version changes
"""

from argparse import ArgumentParser, Namespace, RawDescriptionHelpFormatter
import configparser

import sys
import os
from datetime import datetime, timezone, timedelta
import time
from loguru import logger
from typing import List, Dict, Tuple

from data_pipeline import DataPipeline, DataPipelineConfig
from specialized_capture import SpecializedCapture, special_cases

from util import get_host
import udatetime
import util_git

# ----------------------
parser = ArgumentParser(
    description=__doc__,
    formatter_class=RawDescriptionHelpFormatter)

parser.add_argument(
    '-f', '--format', dest='format_html', action='store_true', default=False,
    help='run the html formater (only)')
parser.add_argument(
    '-c', '--clean', dest='clean_html', action='store_true', default=False,
    help='run the html cleaner (only)')
parser.add_argument(
    '-x', '--extract', dest='extract_html', action='store_true', default=False,
    help='run the html extractor (only)')

parser.add_argument('--trace', dest='trace', action='store_true', default=False,
    help='turn on tracing')
parser.add_argument('-a', '--auto_push', dest='auto_push', action='store_true', default=False,
    help='checkin data to the git repo at end of run')
parser.add_argument('--rerun_now', dest='rerun_now', action='store_true', default=False,
    help='include items that were fetched in the last 15 minutes')
parser.add_argument('--continuous', dest='continuous', action='store_true', default=False,
    help='Run at 0:05 and 0:35')
parser.add_argument('--auto_update', dest='auto_update', action='store_true', default=False,
    help='Pull changes and restart if source has changed')
parser.add_argument('--guarded', dest='guarded', action='store_true', default=False)

parser.add_argument('--firefox', dest='use_firefox', action='store_true', default=False,
    help='capture using firefox')
parser.add_argument('--chrome', dest='use_chrome', action='store_true', default=False,
    help='capture using chrome')
parser.add_argument('--show_browser', dest='show_browser', action='store_true', default=False,
    help='show browser while running')
parser.add_argument('-i', '--image', dest='capture_image', action='store_true', default=False,
    help='capture image after each change')
# data dir args
config = configparser.ConfigParser()
if os.path.exists("data_pipeline.local.ini"):
    config.read('data_pipeline.local.ini')
elif os.path.exists("data_pipeline.ini"):
    config.read('data_pipeline.ini')
else:
    raise Exception("Missing data_pipeline.ini file")

parser.add_argument(
    '--base_dir',
    default=config["DIRS"]["base_dir"],
    help='Local GitHub repo dir for corona19-data-archive')

parser.add_argument(
    '--temp_dir',
    default=config["DIRS"]["temp_dir"],
    help='Local temp dir for snapshots')


# ---- 
def next_time() -> datetime:
    t = datetime.now()
    xmin = t.minute
    if xmin < 25:
        xmin = 35
    elif xmin < 55:
        t = t + timedelta(hours=1)
        xmin = 5
    else:
        t = t + timedelta(hours=1)
        xmin = 35
    t = datetime(t.year, t.month, t.day, t.hour, xmin, 0)
    return t

def init_specialized_capture(args: Namespace) -> SpecializedCapture:
    temp_dir = args.temp_dir
    publish_dir = os.path.join(args.base_dir, "captive-browser")
    capture = SpecializedCapture(temp_dir, publish_dir)
    return capture

def run_continuous(scanner: DataPipeline, capture: SpecializedCapture, auto_push: bool):

    if util_git.monitor_check(): return

    host = get_host()
    try:
        print("starting continuous run")

        scanner.update_sources()
        scanner.process()

        if capture: 
            try:
                special_cases(capture)
            except Exception as ex:
                logger.error(ex)
                logger.error("*** continue after exception in specialized capture")


        if auto_push: util_git.push(scanner.config.base_dir, f"{udatetime.to_logformat(scanner.change_list.start_date)} on {host}")
        if util_git.monitor_check(): return
        cnt = 1
        t = next_time()

        print(f"sleep until {t}")
        while True:
            time.sleep(15)
            if datetime.now() < t: continue

            if util_git.monitor_check(): break

            print("==================================")
            print(f"=== run {cnt} at {t}")
            print("==================================")

            try:
                scanner.update_sources()
                scanner.process()
                if capture: special_cases(capture)
                if auto_push: util_git.push(scanner.config.base_dir, f"{udatetime.to_displayformat(scanner.change_list.start_date)} on {host}")
            except Exception as ex:
                logger.exception(ex)
                print(f"run failed, wait 5 minutes and try again")
                t = t + timedelta(minutes=5)

            print("==================================")
            print("")
            t = next_time()
            print(f"sleep until {t}")                        
            cnt += 1
    finally:
        if capture: capture.close()


def run_once(scanner: DataPipeline, auto_push: bool):
    scanner.update_sources()
    scanner.process()
    if auto_push:
        host = get_host()
        util_git.push(scanner.config.base_dir, f"{udatetime.to_logformat(scanner.change_list.start_date)} on {host}")


def main(args_list=None):

    if args_list is None:
        args_list = sys.argv[1:]
    args = parser.parse_args(args_list)

    if args.auto_update:
        return util_git.monitor_start("--auto_update")
    if not args.auto_push:
        logger.warning("github push is DISABLED")

    config = DataPipelineConfig(args.base_dir, args.temp_dir, flags = {
        "trace": args.trace,
        "capture_image": args.capture_image,
        "rerun_now": args.rerun_now,
        "firefox": args.use_firefox,
        "chrome": args.use_chrome,
        "headless": not args.show_browser,
    })
    scanner = DataPipeline(config)

    capture = init_specialized_capture(args)

    if args.clean_html or args.extract_html or args.format_html:
        if args.format_html: scanner.format_html(rerun=True)
        if args.clean_html: scanner.clean_html(rerun=True)
        if args.extract_html: scanner.extract_html(rerun=True)
    elif args.continuous:
        scanner.format_html()
        scanner.clean_html()
        scanner.extract_html()
        run_continuous(scanner, capture, auto_push = args.auto_push)  
    else:        
        scanner.format_html()
        scanner.clean_html()
        scanner.extract_html()
        run_once(scanner, args.auto_push)


if __name__ == "__main__":
    main()
