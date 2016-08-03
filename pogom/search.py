#!/usr/bin/python
# -*- coding: utf-8 -*-

'''
Search Architecture:
 - Create a Queue
   - Holds a list of locations to scan
 - Create N search threads
   - Each search thread will be responsible for hitting the API for a given scan location
 - Create a "overseer" loop
   - Creates/updates the search grid, populates the Queue, and waits for the current search itteration to complete
   -
'''

import logging
import time
import math
import threading
import random
import maps
import json
from .models import Route, Minion
import pickle


from threading import Thread, Lock
from queue import Queue

from pgoapi import PGoApi
from pgoapi.utilities import f2i, get_cellid

from . import config
from .models import parse_map

log = logging.getLogger(__name__)

TIMESTAMP = '\000\000\000\000\000\000\000\000\000\000\000\000\000\000\000\000\000\000\000\000\000'


search_queue = Queue()


def calculate_lng_degrees(lat):
    return float(lng_gap_meters) / \
        (meters_per_degree * math.cos(math.radians(lat)))


def send_map_request(api, position):
    try:
        api_copy = api.copy()
        api_copy.set_position(*position)
        api_copy.get_map_objects(latitude=f2i(position[0]),
                                 longitude=f2i(position[1]),
                                 since_timestamp_ms=TIMESTAMP,
                                 cell_id=get_cellid(position[0], position[1]))
        return api_copy.call()
    except Exception as e:
        log.warning("Uncaught exception when downloading map " + str(e))
        return False


    
def login(api, args, position, i=0):
    log.info('Attempting login to Pokemon Go.')

    api.set_position(*position)
    print args.pgousers[i][0], args.pgousers[i][1]
    while not api.login(args.auth_service, args.pgousers[i][0], args.pgousers[i][1]):
        log.info('Failed to login to Pokemon Go. Trying again in {:g} seconds.'.format(args.login_delay))
        time.sleep(args.login_delay)

    log.info('Login to Pokemon Go successful.')


#
# Search Threads Logic
#
def create_search_threads(args):
    search_threads = []
    num=len(args.pgousers)
    for i in range(num):
        t = Thread(target=search_thread, name='search_thread-{}'.format(i), args=(i,args,search_queue,))
        t.daemon = True
        t.start()
        search_threads.append(t)


def search_thread(userid,args,q):
    api = PGoApi()
    step =1
    threadname = threading.currentThread().getName()
    log.debug("Search thread {}: started and waiting".format(threadname))
    while True:
        # Get the next item off the queue (this blocks till there is something)
        m, r, lock = q.get()
        waypoints = r.getRoutePoints()
        i=0
        for location in waypoints:
            i=i+1
            with lock:
                if api._auth_provider and api._auth_provider._ticket_expire:
                    remaining_time = api._auth_provider._ticket_expire/1000 - time.time()
            
                    if remaining_time > 60:
                        log.info("Skipping Pokemon Go login process since already logged in \
                            for another {:.2f} seconds".format(remaining_time))
                    else:
                        login(api, args, location[1], userid)
                else:
                    login(api, args, location[1], userid)
            response_dict = {}
            failed_consecutive = 0
            while not response_dict:
                response_dict = send_map_request(api, location[1])
                print '{}: location: {}'.format(args.pgousers[userid][0], location[1])
                if response_dict:
                    with lock:
                        try:
                            parse_map(response_dict, i, step, location[1])
                            log.debug("{}: itteration {} step {} complete".format(threadname, i, step))
                        except KeyError:
                            log.error('Search thread failed. Response dictionary key error')
                            log.debug('{}: itteration {} step {} failed. Response dictionary\
                                key error.'.format(threadname, i, step))
                            failed_consecutive += 1
                            if(failed_consecutive >= config['REQ_MAX_FAILED']):
                                log.error('Niantic servers under heavy load. Waiting before trying again')
                                time.sleep(config['REQ_HEAVY_SLEEP'])
                                failed_consecutive = 0
                            response_dict = {}
                else:
                    log.info('Map download failed, waiting and retrying')
                    log.debug('{}: itteration {} step {} failed'.format(threadname, i, step))
                    print "sleeping {}".format(config['REQ_SLEEP'])
                    time.sleep(config['REQ_SLEEP'])
    
            print "sleeping {}".format(config['REQ_SLEEP'])
            time.sleep(config['REQ_SLEEP'])
        q.task_done()


#
# Search Overseer
#
def search_loop(args):
    i = 0
    while True:
        log.info("Search loop {} starting".format(i))
        try:
            search(args)
            log.info("Search loop {} complete.".format(i))
            i += 1
        except Exception as e:
            log.error('Scanning error @ {0.__class__.__name__}: {0}'.format(e))
        finally:
            if args.thread_delay > 0:
                log.info('Waiting {:g} seconds before beginning new scan.'.format(args.thread_delay))
                time.sleep(args.thread_delay)


#
# Overseer main logic
#
def search(args):

    lock = threading.RLock()
    with lock:
        m = Minion.freeMinion()
        routes = Route.getAllRoutes()
        for r in routes:
            #waypoints = enumerate(generate_location_steps(pickle.loads(r['route_data'])))
            search_args = (m, r, lock)
            search_queue.put(search_args)

    # Wait until this scan itteration queue is empty (not nessearily done)
    while not search_queue.empty():
        log.debug("Waiting for current search queue to complete (remaining: {})".format(search_queue.qsize()))
        time.sleep(1)

    # Don't let this method exit until the last item has ACTUALLY finished
    search_queue.join()


#
# A fake search loop which does....nothing!
#
def fake_search_loop():
    while True:
        log.info('Fake search loop running...')
        time.sleep(10)
