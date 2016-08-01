# coding=utf-8
'''
MAPS -- Version 1, for Python 3

A very simple module for using the Google Maps APIs, with Pokémon GO in mind.


    1) Install 'requests'

        pip install requests

    2) Set your API key (I'm sure you can figure out how to get one)

        >>> import maps
        >>> maps.KEY = ...

       You can also directly edit this file (go line 83)

    3) That is all.


There are only two functions.

    * coordinates(location)

        It converts the name of a location into its coordinates.

            >>> coordinates('Paris')
            (48.856614, 2.3522219)

        If something goes wrong, the location isn't found, etc, it will return
        None.

    * path(origin, destination = None, mode = 'walking')

        This is by far the most useful and interesting function, I think.
        It returns a "path", which is just a list of coordinates to follow.

            >>> path(coordinates('Paris'), coordinates('London'))
            [(48.85668, 2.35196), (48.86142, 2.33929), (48.86897, 2.32369), ...

        The path follows existing roads, so your walk will look more "human".

        Now, the best part: the function also works on a list of coordinates.
        Let's say you want to visit a set of PokéStops: simply pass the list
        of coordinates, and voilà.

            >>> path([(..., ...), (..., ...), ...])
            [(..., ...), ...

        And it will try to find the shortest path going through all of them
        (aka solving the Travelling Salesman Problem). Isn't that wonderful?

        Finally, if walking doesn't suit you, you can change that by setting
        'mode' to something else, like, 'bicycle'.


        More informations at
        https://developers.google.com/maps/documentation/directions/intro


Pros:

    - Python 3
    - Very simple and easy to use
    - No crazy dependencies

Cons:

    - Python 3
    - Returns None if anything goes wrong, with no additional information.
    - The code smells


Oh, and DO WHAT THE FUCK YOU WANT WITH THIS.
'''
from urllib import urlencode
from requests import get



# Replace with your API key here!
#from . import config
KEY = "AIzaSyCdsNNCkw0WiOhriFVGqjiSJDcb5p3YSW4"



def _fetch(api, args):
    base_url = 'https://maps.googleapis.com/maps/api/%s/json?key=%s&'
    return get(base_url % (api, KEY) + urlencode(args)).json()

def _decode(polyline):
    values, current = [], []
    for byte in bytearray(polyline, 'ascii'):
        byte -= 63
        current.append(byte & 0x1f)
        if byte & 0x20:
            continue
        value = 0
        for chunk in reversed(current):
            value <<= 5
            value |= chunk
        values.append(((~value if value & 0x1 else value) >> 1) / 100000.)
        current = []
    result, x, y = [], 0., 0.
    for dx, dy in [tuple(values[i:i+2]) for i in range(0, len(values), 2)]:
        x, y = x + dx, y + dy
        result.append((round(x, 6), round(y, 6)))
    return result



def coordinates(location):
    '''
    Get the coordinates of a given location.

        >>> coordinates('Paris')
        (48.856614, 2.3522219)

    Returns None if it didn't work.
    '''

    try:

        result = _fetch('geocode', {'address': location})
        result = result['results'][0]['geometry']['location']

    except:

        return None

    return result['lat'], result['lng']


def path(origin, destination = None, mode = 'walking'):
    '''
    Find a not-so-long path from somewhere to somewhere else.

    'origin' and 'destination' must be coordinates.
    If 'destination' is omitted, 'origin' must be a list of coordinates.

        >>> path(coordinates('Paris'), coordinates('London'))
        [(48.85668, 2.35196), (48.86142, 2.33929), (48.86897, 2.32369), ...

    Returns a list of coordinates to follow, or None if it didn't work either.
    '''
    print origin, destination
    args = {'mode': mode}
    if destination:
        origin, destination = '%f,%f' % origin, '%f,%f' % destination
    else:
        points = ['%f,%f' % coordinates for coordinates in origin]
        origin, destination = points[0], points[-1]
        if len(points) > 2:
            args = {'waypoints': 'optimize:true|via:' + '|via:'.join(points[1:-1])}
    args.update({'origin': origin, 'destination': destination})
    #try:
    result = _fetch('directions', args)
    # You can extract other useful informations here, such as duration
    result = result['routes'][0]['overview_polyline']['points']
    #except:
        #return None
    return _decode(result)
