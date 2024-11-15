# Copyright 2024 Davide Gessa

# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at

# http://www.apache.org/licenses/LICENSE-2.0

# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.

import re
import os
import sys
import shutil
import subprocess
import requests
import tarfile
import json


REPO_URL = 'gavofyork/graypaper'
META_DIR = './paper_metadata/'
MIN_VER = '0.4.0'

def extract_formulas(aux_file, tex_files):
    formulas = {}

    with open(aux_file, 'r') as file:
        for line in file:
            if line.startswith('\\newlabel'):
                match = re.search(r'\{(.*?)\}\{\{(.*?)\}\}', line)
                if match:
                    formula_label = match.group(1)
                    formula_index = match.group(2)
                    formulas[formula_label] = {'index': formula_index.split('}')[0], 'text': None, 'label': formula_label}

    for tex_file in tex_files:
        with open(tex_file, 'r') as file:
            content = file.read()
            formula_matches = re.findall(r'\\begin\{(align|equation)\}(.*?)\\end\{\1\}', content, re.DOTALL)
            for formula_type, formula_text in formula_matches:
                formula_label = next((label for label, info in formulas.items() if info['text'] is None), None)
                if formula_label:
                    formulas[formula_label]['text'] = formula_text.strip()

    return formulas

def download_file(url, local_path):
    response = requests.get(url, stream=True)
    with open(local_path, 'wb') as file:
        shutil.copyfileobj(response.raw, file)

def extract_tarball(tarball_path, extract_dir):
    with tarfile.open(tarball_path, 'r:gz') as tar:
        tar.extractall(extract_dir)

def download_releases(local_dir):
    api_url = f"https://api.github.com/repos/{REPO_URL}/releases"
    response = requests.get(api_url)
    releases = response.json()

    for release in releases:
        if release['tag_name'] == f'v{MIN_VER}':
            break 
        
        release_dir = os.path.join(local_dir, release['tag_name'])
        
        if os.path.exists(release_dir + '.json'):
            print(f'Release {release['tag_name']} already present, skipping.')
            continue
            
            
        print(f'Downloading release {release['tag_name']}')
        
        if not os.path.exists(release_dir):
            os.makedirs(release_dir)       
              
        asset_url = release['tarball_url']
        asset_path = os.path.join(release_dir, release['tag_name'] + '.tar')
        download_file(asset_url, asset_path)
        extract_tarball(asset_path, release_dir)
        os.remove(asset_path)
        
        gp_dir = os.path.join(release_dir, os.listdir(release_dir)[0])
        print('Building', gp_dir)

        tex_file = os.path.join('graypaper.tex')
        # aux_file = os.path.join(release_dir, 'graypaper.aux')
        # if not os.path.exists(aux_file):
        subprocess.run(['xelatex', '-halt-on-error', tex_file], cwd=gp_dir)
        
        print('Preparing db:', release_dir + '.json')
        tex_files = list(map(lambda f: os.path.join(gp_dir, 'text', f), os.listdir(os.path.join(gp_dir, 'text'))))
        formulas = extract_formulas(os.path.join(gp_dir, 'graypaper.aux'), tex_files)
        
        f = open(release_dir + '.json', 'w')
        f.write(json.dumps(list(formulas.values())))
        f.close()
        
        shutil.rmtree(release_dir)

    return releases[0]['tag_name'][1:]

def create_db(meta_dir):
    versions = os.listdir(meta_dir)
    db = {}
    
    for v in versions:
        with open(os.path.join(meta_dir, v), 'r') as f:
            data = json.loads(f.read())
        db[v.replace('v', '').replace('.json', '')] = data 
    
    return db



def find_code_tags(directory):
    matches = []

    for root, dirs, files in os.walk(directory):
        for file in files:
            file_path = os.path.join(root, file)
            try:
                with open(file_path, 'r') as f:
                    content = f.read()
                    for line_num, line in enumerate(content.splitlines(), start=1):
                        for match in re.finditer(r'\$\((.*?)\)', line):
                            full_match = match.group(1)
                            
                            version, index = full_match.split('-')
                            version = version.strip()
                            index = index.strip()
                            indexes = index.split('/')
                            
                            for i in indexes:
                                matches.append((file_path, line_num, version, i.strip()))
            except UnicodeDecodeError:
                # Skip non-text files
                continue

    return matches


def run():
    if len(sys.argv) < 2:
        print('usage: python jambiato.py /path/to/your/code')
        return
        
    code_path = sys.argv[1]
    
    # Fetch releases
    latest = download_releases(META_DIR)
    
    # Create version db
    db = create_db(META_DIR)
    
    # Get all code tags    
    tags = find_code_tags(code_path)
    
    print("\nProcessing code...")
    
    outdated = []
    missing = []
    unrecognized = []
    
    for t in tags:
        (file, line, version, index) = t
        
        if version != latest:
            outdated.append(t)
            
        matches = list(filter(lambda x: x['index'].find(index) != -1, db[version]))
        if len(matches) == 0:
            unrecognized.append(t)
            
            
    # Check for missing tags
    for t in db[latest]:
        matches = list(filter(lambda x: t['index'].find(x[3]) != -1, tags))
        if len(matches) > 0:
            missing.append(t)
            
    if len(missing) == 0 and len(outdated) == 0 and len(unrecognized) == 0:
        print ("Your code is up to date")
        return 
    
    outdated.sort(key=lambda x: x[3])
    unrecognized.sort(key=lambda x: x[3])
    
    
    print(f"There are {len(missing)} missing definitions:")
    for t in missing:
        print('\t',t['index'], t['label'])
        
    print(f"There are {len(outdated)} outdated tags (latest is: {latest})")
    for t in outdated:
        (file, line, version, index) = t
        print('\t',t)
        
    print(f"There are {len(unrecognized)} unrecognized tags:")
    for t in unrecognized:
        (file, line, version, index) = t
        print('\t',t)
        
        
    

if __name__ == "__main__":
    run ()