#!/usr/bin/env python
"""pywamgr - The Python WoW Addon Manager

Usage:
    pywamgr.py install <addon>...
    pywamgr.py update (<addon>... | --all)
    pywamgr.py remove <addon>...
    pywamgr.py -h | --help
    pywamgr.py --version

Options:
    -h --help  Show this screen.
    --version  Show version.
    --all      Update all addons.
    <addon>    Addon name
"""

from bs4 import BeautifulSoup, SoupStrainer
from docopt import docopt
from os.path import expanduser, dirname, basename, isfile, isdir
from zipfile import ZipFile
import gzip
import hashlib
import io
import json
import os
import requests
import shutil
import sys
import yaml

def get_curse_addon_data(addon):
    base_url = 'https://www.curseforge.com/wow/addons/{}/'.format(addon)
    project_url = base_url + 'files?sort=releasetype'

    r = requests.get(project_url)
    soup = BeautifulSoup(r.content, 'html.parser', parse_only=SoupStrainer('a'))
    elem = soup.find('a', {'class': 'mg-r-05'})['data-action-value']
    data = json.loads(elem)

    return [data['FileName'].strip(), base_url +
            "download/{}/file".format(data['ProjectFileID'])]

# Updates addon if it's not already up-to-date
def update_addon(addon, addons_dir):
    project_data = get_curse_addon_data(addon)

    new_version = project_data[0]
    cachepath = '.cache/' + addon
    version_file = cachepath + '/VERSION'
    try:
        with open(version_file, 'r') as fd:
            old_version = fd.read()

        if old_version == new_version:
            if check_addon(addon, addons_dir):
                print(addon + ' is already up-to-date.')
                return

            print(addon + ' seems to be broken. Reinstalling.')

        remove_addon(addon, addons_dir)
        print('Updating ' + addon + ' (' + old_version + ' -> ' + new_version
                + ')')
    except OSError:
        try:
            os.makedirs(cachepath)
        except:
            pass

    with open(version_file, 'w') as out:
        out.write(new_version)

    r = requests.get(project_data[1], stream=True)

    mtree = []
    with ZipFile(io.BytesIO(r.content)) as z:
        for name in z.namelist():
            m = hashlib.sha256()
            path = addons_dir + name

            try:
                os.makedirs(dirname(path))
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

def remove_addon(addon, addons_dir):
    cachepath = '.cache/' + addon

    try:
        with gzip.open(cachepath + '/MTREE', 'rt') as data_file:
            data = json.load(data_file)

        for entry in data:
            try:
                os.remove(addons_dir + entry[0])
            except FileNotFoundError:
                pass

        for root, dirs, _ in os.walk(addons_dir, topdown=False):
            for name in dirs:
                try:
                    os.rmdir(os.path.join(root, name))
                except OSError:
                    pass
    except FileNotFoundError:
        print('ERROR: MTREE for ' + addon + ' could not be found.'
              ' Nothing has been removed.')

if __name__ == '__main__':
    args = docopt(__doc__, version='0.1-alpha')

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

        for addon in addons:
            if not addon in cfg['addons']:
                cfg['addons'].append(addon)
                cfg_changed = True

            update_addon(addon, install_dir)

    if args['remove']:
        for addon in args['<addon>']:
            try:
                cfg['addons'].remove(addon)
                cfg_changed = True
            except ValueError:
                print(addon + " is not installed and thus cannot be removed.")
                continue

            remove_addon(addon, install_dir)
            shutil.rmtree('.cache/' + addon)

    # save new configuration
    if cfg_changed:
        with open(config_file, 'w') as yamlfile:
            yaml.dump(cfg, yamlfile)
