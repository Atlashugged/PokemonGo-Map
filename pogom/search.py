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

def get_new_coords(init_loc, distance, bearing):
    """ Given an initial lat/lng, a distance(in kms), and a bearing (degrees),
    this will calculate the resulting lat/lng coordinates.
    """ 
    R = 6378.1 #km radius of the earth
    bearing = math.radians(bearing)

    init_coords = [math.radians(init_loc[0]), math.radians(init_loc[1])] # convert lat/lng to radians

    new_lat = math.asin( math.sin(init_coords[0])*math.cos(distance/R) +
        math.cos(init_coords[0])*math.sin(distance/R)*math.cos(bearing))
    new_lon = init_coords[1] + math.atan2(math.sin(bearing)*math.sin(distance/R)*math.cos(init_coords[0]),
        math.cos(distance/R)-math.sin(init_coords[0])*math.sin(new_lat))
    
    wobble_lat = new_lat + (random.uniform(0.00000001,0.0000015) * random.choice([-1,1]))
    wobble_lon = new_lon + (random.uniform(0.00000001,0.0000015) * random.choice([-1,1]))
    print "lat: {}, lon: {}".format(new_lat, new_lon)
    print "wob: {}, wlb: {}".format(wobble_lat, wobble_lon)
    return [math.degrees(wobble_lat), math.degrees(wobble_lon)]

def generate_location_steps(route):
    time.sleep(1)
    homedest = maps.coordinates(route[0])
    waydest = maps.coordinates(route[1])
    loopdest = maps.coordinates(route[2])
    
    yield maps.getElevation(homedest)
    speed=11+random.choice([-3,-2,-1,0,1,2])
    mpath = maps.path(homedest, waydest, speed=speed)
    for s in mpath:
        yield (randomizeCoords((s[0],s[1],s[2])))
    
    mpath = maps.path(waydest, loopdest, speed=speed)
    for s in mpath:
        yield (randomizeCoords((s[0],s[1],s[2])))
        
    mpath = maps.path(loopdest, homedest, speed=speed)
    for s in mpath:
        yield (randomizeCoords((s[0],s[1],s[2])))

def randomizeCoords(coords):
    lat = coords[0]
    lon = coords[1]
    z = coords[2]
    lat = lat + (random.uniform(0.00000001,0.0000013) * random.choice([-1,1]))
    lon = lon + (random.uniform(0.00000001,0.0000013) * random.choice([-1,1]))
    return(lat,lon,z)
    
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
        route, lock = q.get()
        i=0
        for loc in route:
            i=i+1
            if api._auth_provider and api._auth_provider._ticket_expire:
                remaining_time = api._auth_provider._ticket_expire/1000 - time.time()
        
                if remaining_time > 60:
                    log.info("Skipping Pokemon Go login process since already logged in \
                        for another {:.2f} seconds".format(remaining_time))
                else:
                    login(api, args, loc[1], userid)
            else:
                login(api, args, loc[1], userid)
            response_dict = {}
            failed_consecutive = 0
            while not response_dict:
                response_dict = send_map_request(api, loc[1])
                print '{}: location: {}'.format(args.pgousers[userid][0], loc[1])
                if response_dict:
                    with lock:
                        try:
                            parse_map(response_dict, i, step, loc[1])
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

    position = (config['ORIGINAL_LATITUDE'], config['ORIGINAL_LONGITUDE'], 0)

    lock = Lock()
    with lock:
        for r in args.routes:
            waypoints = enumerate(generate_location_steps(r))
            search_args = (waypoints, lock)
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
