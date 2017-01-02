#!/usr/bin/env python
"""pywamgr - The Python WoW Addon Manager

Usage:
    wad.py install <addon>...
    wad.py update (<addon>... | --all)
    wad.py remove <addon>...
    wad.py -h | --help
    wad.py --version

Options:
    -h --help  Show this screen.
    --version  Show version.
    --all      Update all addons.
    <addon>    Addon name
"""

from bs4 import BeautifulSoup, SoupStrainer
from docopt import docopt
from multiprocessing import Pool
from os import makedirs
from os.path import expanduser, dirname, basename, isfile, isdir, splitext
from zipfile import ZipFile
import gzip
import hashlib
import io
import json
import requests
import sys
import yaml

def get_curse_addon_url(addon):
    base_url = 'https://mods.curse.com/addons/wow/'
    headers = {'user-agent': 'Mozilla/5.0'} # TODO: not needed?

    r = requests.get(base_url + addon + '/download', headers=headers)

    soup = BeautifulSoup(r.content, 'html.parser', parse_only=SoupStrainer('a'))

    link = soup.find('a', {'class': 'download-link'})['data-href']

    # replace http url with https
    return link.replace('http://addons.curse', 'https://addons-origin')

# Updates addon if it's not already up-to-date
def update_addon(addon, outpath):
    url = get_curse_addon_url(addon)

    new_version = splitext(basename(url))[0]
    cachepath = '.cache/' + addon
    version_file = cachepath + '/VERSION'
    try:
        with open(version_file, 'r') as fd:
            old_version = fd.read()

        if old_version == new_version:
            if check_addon(addon, outpath):
                print(addon + ' is already up-to-date.')
                return

            print(addon + ' seems to be broken. Reinstalling.')
    except:
        try:
            makedirs(cachepath)
        except:
            pass

    with open(version_file, 'w') as out:
        out.write(new_version)

    r = requests.get(url, stream=True)

    mtree = []
    with ZipFile(io.BytesIO(r.content)) as z:
        for name in z.namelist():
            m = hashlib.sha256()
            path = outpath + name

            try:
                makedirs(dirname(path))
            except:
                pass

            if isdir(path):
               continue

            with open(path, 'wb') as out, z.open(name) as zfile:
                while True:
                    chunk = zfile.read(4096)
                    if not chunk:
                        break
                    m.update(chunk)
                    out.write(chunk)

            mtree.append([name, m.hexdigest()])

        with gzip.open(cachepath + '/MTREE', 'wt') as gz:
            json.dump(mtree, gz)

    print('Finished installing ' + addon + '.')

# Check if addon is correctly installed
def check_addon(addon, addons_dir):
    cachepath = '.cache/' + addon
    try:
        with gzip.open(cachepath + '/MTREE', 'rt') as data_file:
            data = json.load(data_file)
    except:
        # cache file does not exist
        return False

    for entry in data:
        m = hashlib.sha256()
        try:
            with open(addons_dir + entry[0], 'rb') as f:
                while True:
                    chunk = f.read(4096)
                    if not chunk:
                        break
                    m.update(chunk)

            if m.hexdigest() != entry[1]:
                # hash doen't match
                return False
        except FileNotFoundError:
            # addon file is missing
            return False

    return True

if __name__ == '__main__':
    args = docopt(__doc__, version='0.1-alpha')
    print(args)

    config_file = expanduser('~/.pywamgr.yaml')

    try:
        with open(config_file) as yamlfile:
            cfg = yaml.load(yamlfile)

    except FileNotFoundError:
        # load and dump default configuration
        cfg = yaml.load("""
            wow_directory: C:/Program Files/World of Warcraft
            addons: []
        """)

    print(cfg)
    cfg_changed = False
    install_dir = cfg['wow_directory'] + '/Interface/AddOns/'

    # check if wow_directory is correct
    if not isfile(cfg['wow_directory'] + '/Wow.exe'):
        print('Warning: no WoW installation found at ' + cfg['wow_directory'])

    if args['install'] or args['update']:
        if args['--all']:
            addons = cfg['addons']
        else:
            addons = args['<addon>']

        with Pool(32) as p:
            for addon in addons:
                if not addon in cfg['addons']:
                    cfg['addons'].append(addon)
                    cfg_changed = True

                p.apply_async(update_addon, args = (addon, install_dir))

            p.close()
            p.join()
    if args['remove']:
        for addon in args['<addon>']:
            print('Not implemented')

    # save new configuration
    if cfg_changed:
        with open(config_file, 'w') as yamlfile:
            yaml.dump(cfg, yamlfile)
