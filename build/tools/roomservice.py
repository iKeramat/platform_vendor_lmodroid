#!/usr/bin/env python
# Copyright (C) 2012-2013, The CyanogenMod Project
#           (C) 2017-2018,2020-2021, The LineageOS Project
#           (C) 2020       The LibreMobileOS Foundation
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#      http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.

from __future__ import print_function

import base64
import json
import netrc
import os
import re
import sys
try:
  # For python3
  import urllib.error
  import urllib.parse
  import urllib.request
except ImportError:
  # For python2
  import imp
  import urllib2
  import urlparse
  urllib = imp.new_module('urllib')
  urllib.error = urllib2
  urllib.parse = urlparse
  urllib.request = urllib2

from xml.etree import ElementTree

product = sys.argv[1]

if len(sys.argv) > 2:
    depsonly = sys.argv[2]
else:
    depsonly = None

try:
    device = product[product.index("_") + 1:]
except:
    device = product

if not depsonly:
    print("Device %s not found. Attempting to retrieve device repository from LMODroid-Devices of LMO Git (https://git.libremobileos.com/LMODroid-Devices)." % device)

repositories = []

try:
    authtuple = netrc.netrc().authenticators("git.libremobileos.com")

    if authtuple:
        gitlmoauth = authtuple[0]
    else:
        gitlmoauth = None
except:
    gitlmoauth = None

def add_auth(gitlmoreq):
    if gitlmoauth:
        gitlmoreq.add_header("Authorization","Bearer %s" % gitlmoauth)

if not depsonly:
    gitlmoreq = urllib.request.Request("https://git.libremobileos.com/api/v4/groups/LMODroid-Devices")
    add_auth(gitlmoreq)
    try:
        result = json.loads(urllib.request.urlopen(gitlmoreq).read().decode())
    except urllib.error.URLError:
        print("Failed to get devices repos")
        sys.exit(1)
    except ValueError:
        print("Failed to parse return data from LMO git")
        sys.exit(1)
    for project in result.get('projects', []):
        if device in project["name"]:
            repositories.append(project)

local_manifests = r'.repo/local_manifests'
if not os.path.exists(local_manifests): os.makedirs(local_manifests)

def exists_in_tree(lm, path):
    for child in lm.getchildren():
        if child.attrib['path'] == path:
            return True
    return False

# in-place prettyprint formatter
def indent(elem, level=0):
    i = "\n" + level*"  "
    if len(elem):
        if not elem.text or not elem.text.strip():
            elem.text = i + "  "
        if not elem.tail or not elem.tail.strip():
            elem.tail = i
        for elem in elem:
            indent(elem, level+1)
        if not elem.tail or not elem.tail.strip():
            elem.tail = i
    else:
        if level and (not elem.tail or not elem.tail.strip()):
            elem.tail = i

def get_manifest_path():
    '''Find the current manifest path
    In old versions of repo this is at .repo/manifest.xml
    In new versions, .repo/manifest.xml includes an include
    to some arbitrary file in .repo/manifests'''

    m = ElementTree.parse(".repo/manifest.xml")
    try:
        m.findall('default')[0]
        return '.repo/manifest.xml'
    except IndexError:
        return ".repo/manifests/{}".format(m.find("include").get("name"))

def get_default_revision():
    m = ElementTree.parse(".repo/manifests/snippets/lmodroid.xml")
    d = m.findall('remote')
    for n in d:
        if n.get('name') == 'lmodroid':
            r = n.get('revision')
            return r.replace('refs/heads/', '').replace('refs/tags/', '')

def get_from_manifest(devicename):
    try:
        lm = ElementTree.parse(".repo/local_manifests/roomservice.xml")
        lm = lm.getroot()
    except:
        lm = ElementTree.Element("manifest")

    for localpath in lm.findall("project"):
        if re.search("device_.*_%s$" % device, localpath.get("name")):
            return localpath.get("path")

    return None

def is_in_manifest(projectpath):
    try:
        lm = ElementTree.parse(".repo/local_manifests/roomservice.xml")
        lm = lm.getroot()
    except:
        lm = ElementTree.Element("manifest")

    for localpath in lm.findall("project"):
        if localpath.get("path") == projectpath:
            return True

    # Checkout removed projects
    removed_projects = []
    try:
        lm = ElementTree.parse(".repo/manifests/snippets/remove.xml")
        lm = lm.getroot()
    except:
        lm = ElementTree.Element("manifest")

    for localpath in lm.findall("remove-project"):
        removed_projects.append(localpath.get("name"))

    # Search in main manifest, too
    try:
        lm = ElementTree.parse(get_manifest_path())
        lm = lm.getroot()
    except:
        lm = ElementTree.Element("manifest")

    for localpath in lm.findall("project"):
        if localpath.get("path") == projectpath and localpath.get("name") not in removed_projects:
            return True

    # ... and don't forget the lmodroid snippet
    try:
        lm = ElementTree.parse(".repo/manifests/snippets/lmodroid.xml")
        lm = lm.getroot()
    except:
        lm = ElementTree.Element("manifest")

    for localpath in lm.findall("project"):
        if localpath.get("path") == projectpath and localpath.get("name") not in removed_projects:
            return True

    return False

def add_to_manifest(repositories, fallback_branch = None):
    try:
        lm = ElementTree.parse(".repo/local_manifests/roomservice.xml")
        lm = lm.getroot()
    except:
        lm = ElementTree.Element("manifest")

    for repository in repositories:
        repo_name = repository['repository']
        repo_target = repository['target_path']
        print('Checking if %s is fetched from %s' % (repo_target, repo_name))
        if is_in_manifest(repo_target):
            print('%s already fetched to %s' % (repo_name, repo_target))
            continue

        if 'remote' in repository:
            repo_remote=repository['remote']
        else:
            repo_remote='lmodroid'

        print('Adding dependency: %s' % repo_name)
        project = ElementTree.Element("project", attrib = { "path": repo_target,
            "remote": repo_remote, "name": repo_name })

        if 'branch' in repository:
            project.set('revision',repository['branch'])
        elif fallback_branch:
            print("Using fallback branch %s for %s" % (fallback_branch, repo_name))
            project.set('revision', fallback_branch)
        else:
            print("Using default branch for %s" % repo_name)

        lm.append(project)

    indent(lm, 0)
    raw_xml = ElementTree.tostring(lm).decode()
    raw_xml = '<?xml version="1.0" encoding="UTF-8"?>\n' + raw_xml

    f = open('.repo/local_manifests/roomservice.xml', 'w')
    f.write(raw_xml)
    f.close()

def fetch_dependencies(repo_path, fallback_branch = None):
    print('Looking for dependencies in %s' % repo_path)
    dependencies_path = repo_path + '/lmodroid.dependencies'
    syncable_repos = []
    verify_repos = []

    if os.path.exists(dependencies_path):
        dependencies_file = open(dependencies_path, 'r')
        dependencies = json.loads(dependencies_file.read())
        fetch_list = []

        for dependency in dependencies:
            if not is_in_manifest(dependency['target_path']):
                fetch_list.append(dependency)
                syncable_repos.append(dependency['target_path'])
                verify_repos.append(dependency['target_path'])
            else:
                verify_repos.append(dependency['target_path'])

            if not os.path.isdir(dependency['target_path']):
                syncable_repos.append(dependency['target_path'])

        dependencies_file.close()

        if len(fetch_list) > 0:
            print('Adding dependencies to manifest')
            add_to_manifest(fetch_list, fallback_branch)
    else:
        print('%s has no additional dependencies.' % repo_path)

    if len(syncable_repos) > 0:
        print('Syncing dependencies')
        os.system('repo sync --force-sync %s' % ' '.join(syncable_repos))

    for deprepo in verify_repos:
        fetch_dependencies(deprepo)

def has_branch(branches, revision):
    return revision in [branch['name'] for branch in branches]

if depsonly:
    repo_path = get_from_manifest(device)
    if repo_path:
        fetch_dependencies(repo_path)
    else:
        print("Trying dependencies-only mode on a non-existing device tree?")

    sys.exit()

else:
    for repository in repositories:
        repo_name = repository['name']
        if re.match(r"^device_[^_]*_" + device + "$", repo_name):
            print("Found repository: %s" % repository['name'])
            
            manufacturer = repo_name.replace("device_", "").replace("_" + device, "")
            
            default_revision = get_default_revision()
            print("Default revision: %s" % default_revision)
            print("Checking branch info")
            gitlmoreq = urllib.request.Request(repository['_links']['repo_branches'])
            add_auth(gitlmoreq)
            result = json.loads(urllib.request.urlopen(gitlmoreq).read().decode())

            ## Try tags, too, since that's what releases use
            if not has_branch(result, default_revision):
                result.extend (repository['tag_list'])
            
            repo_path = "device/%s/%s" % (manufacturer, device)
            adding = {'repository':repository['path_with_namespace'],'target_path':repo_path}
            
            fallback_branch = None
            if not has_branch(result, default_revision):
                if os.getenv('ROOMSERVICE_BRANCHES'):
                    fallbacks = list(filter(bool, os.getenv('ROOMSERVICE_BRANCHES').split(' ')))
                    for fallback in fallbacks:
                        if has_branch(result, fallback):
                            print("Using fallback branch: %s" % fallback)
                            fallback_branch = fallback
                            break

                if not fallback_branch:
                    print("Default revision %s not found in %s. Bailing." % (default_revision, repo_name))
                    print("Branches found:")
                    for branch in [branch['name'] for branch in result]:
                        print(branch)
                    print("Use the ROOMSERVICE_BRANCHES environment variable to specify a list of fallback branches.")
                    sys.exit()

            add_to_manifest([adding], fallback_branch)

            print("Syncing repository to retrieve project.")
            os.system('repo sync --force-sync %s' % repo_path)
            print("Repository synced!")

            fetch_dependencies(repo_path, fallback_branch)
            print("Done")
            sys.exit()

print("Repository for %s not found in the LMODroid Git repository list. If this is in error, you may need to manually add it to your local_manifests/roomservice.xml." % device)
