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

from string import ascii_uppercase
from typing import List

from TexSoup import TexSoup

REPO_URL = "gavofyork/graypaper"
META_DIR = "./paper_metadata/"
MIN_VER = "0.4.0"


def extract_sections_and_formulas(tex_soup, section_div):
    result = []
    current_section = None
    formula_counter = 1
    is_appendix = False
    section_counter = 1

    def get_section_number(is_appendix, counter):
        if is_appendix:
            return ascii_uppercase[counter - 1]
        return str(counter)

    def process_equation(eq, section_num) -> List:
        nonlocal formula_counter

        if str(eq.name) == "align" and len(str(eq).split("\\\\")) > 1:
            eqs = []
            i = 0
            data = str(eq).split("\\\\")
            x = data[i]

            # Handle the case where the first line contains a nonumber
            if x.find("\\nonumber") != -1:
                i += 1
                x = data[i]

            while i < len(data):
                if (
                    (x.count("\\begin{cases}") != x.count("\\end{cases}"))
                    or (x.count("\\begin{rcases}") != x.count("\\end{rcases}"))
                    or (x.count("\\begin{aligned}") != x.count("\\end{aligned}"))
                    or (x.count("\\begin{align*}") != x.count("\\end{align*}"))
                ):
                    i += 1
                    x += data[i]
                    continue

                if (i + 1) < len(data) and data[i + 1].find("\\nonumber") != -1:
                    i += 1
                    x += data[i]
                    continue

                if section_div:
                    formula_idx = f"{section_num}.{formula_counter}"
                else:
                    formula_idx = f"{formula_counter}"

                label = None
                if x.find("\\label{") != -1:
                    label = x.split("\\label{")[1].split("}")[0]

                eqs.append(["formula", label, formula_idx, x])
                formula_counter += 1
                i += 1
                if i < len(data):
                    x = data[i]

            return eqs

        label = None

        # Get the raw LaTeX code
        formula_tex = str(eq)

        # Try to find label in the equation
        labels = eq.find_all("label")
        if labels:
            label = str(labels[0].string)

        if label is None and formula_tex.find("\\label{") != -1:
            label = x.split("\\label{")[1].split("}")[0]

        # Create formula index
        if section_div:
            formula_idx = f"{section_num}.{formula_counter}"
        else:
            formula_idx = f"{formula_counter}"

        formula_counter += 1

        return [["formula", label, formula_idx, formula_tex]]

    def process_node(node):
        nonlocal current_section, section_counter, is_appendix, formula_counter

        # Check if it's the appendix
        if str(node.name) == "appendix":
            is_appendix = True
            section_counter = 1
            return

        # Check if it's the label
        if (
            str(node.name) == "label"
            and result[-1][0] == "section"
            and result[-1][1] is None
            and node.args[0].string.find("sec:") != -1
        ):
            result[-1][1] = node.args[0].string

        # Process sections
        if str(node.name) == "section":
            section_num = get_section_number(is_appendix, section_counter)
            current_section = section_num
            section_title = node.args[0].string

            result.append(["section", None, section_num, section_title])
            section_counter += 1

            # Reset formula counter for new section
            if section_div:
                formula_counter = 1

        # Process equations
        elif str(node.name) in ["equation", "align", "gather"]:
            if current_section:  # Only process if we're in a section
                result.extend(process_equation(node, current_section))
            else:
                raise Exception("Formula outside section")

        # Recursively process children
        if hasattr(node, "contents"):
            for child in node.contents:
                if hasattr(child, "name"):  # Only process TeX nodes
                    process_node(child)

    # Start processing from root
    for node in tex_soup.contents:
        if hasattr(node, "name"):
            process_node(node)

    return result


def process_tex_inputs(base_dir, current_file):
    with open(current_file, "r", encoding="utf-8") as f:
        content = f.read().split("\n")

        content = list(filter(lambda x: x.find("newcommand") == -1, content))
        content = "\n".join(content)

    pattern = r"\\input\s*\{([^}]+)\}"

    def expand_match(match):
        input_file = match.group(1)
        if not input_file.endswith(".tex"):
            input_file += ".tex"

        full_path = os.path.join(base_dir, input_file)

        try:
            return process_tex_inputs(base_dir, full_path)
        except FileNotFoundError:
            return ""

    return re.sub(pattern, expand_match, content)


def extract_formulas_soup(gp_dir, tex_file, tex_files, section_div):
    formulas = {}

    data = process_tex_inputs(gp_dir, os.path.join(gp_dir, tex_file))
    soup = TexSoup(data)

    res = extract_sections_and_formulas(soup, section_div)
    formulas = {}
    for x in res:
        if x[0] != "formula":
            continue

        label, formula_idx, formula_tex = x[1:]
        print(formula_idx, "\t\t", label)
        formulas[formula_idx] = {
            "label": label,
            "index": formula_idx,
            "tex": formula_tex,
        }

    print(f"Extracted {len(formulas)} formulas")

    return formulas


def download_file(url, local_path):
    response = requests.get(url, stream=True)
    with open(local_path, "wb") as file:
        shutil.copyfileobj(response.raw, file)


def extract_tarball(tarball_path, extract_dir):
    with tarfile.open(tarball_path, "r:gz") as tar:
        tar.extractall(extract_dir)


def download_releases(local_dir):
    api_url = f"https://api.github.com/repos/{REPO_URL}/releases"
    response = requests.get(api_url)
    releases = response.json()

    for release in releases:
        if release["tag_name"] == f"v{MIN_VER}":
            break

        release_dir = os.path.join(local_dir, release["tag_name"])

        if os.path.exists(release_dir + ".json"):
            print(f"Release {release['tag_name']} already present, skipping.")
            continue

        print(f"Downloading release {release['tag_name']}")

        if not os.path.exists(release_dir):
            os.makedirs(release_dir)

        asset_url = release["tarball_url"]
        asset_path = os.path.join(release_dir, release["tag_name"] + ".tar")
        download_file(asset_url, asset_path)
        extract_tarball(asset_path, release_dir)
        os.remove(asset_path)

        gp_dir = os.path.join(release_dir, os.listdir(release_dir)[0])
        print("Building", gp_dir)

        tex_file = os.path.join("graypaper.tex")

        print("Preparing db:", release_dir + ".json")
        tex_files = list(
            map(
                lambda f: os.path.join(gp_dir, "text", f),
                os.listdir(os.path.join(gp_dir, "text")),
            )
        )
        formulas = extract_formulas_soup(
            gp_dir, tex_file, tex_files, section_div=int(release["tag_name"][3]) > 4
        )

        f = open(release_dir + ".json", "w")
        f.write(json.dumps(list(formulas.values()), separators=(",\n", ": ")))
        f.close()

        shutil.rmtree(release_dir)

    return releases[0]["tag_name"][1:]


def create_db(meta_dir):
    versions = os.listdir(meta_dir)
    db = {}

    for v in versions:
        with open(os.path.join(meta_dir, v), "r") as f:
            data = json.loads(f.read())
        db[v.replace("v", "").replace(".json", "")] = data

    return db


def find_code_tags(directory):
    matches = []

    for root, dirs, files in os.walk(directory):
        for file in files:
            file_path = os.path.join(root, file)
            try:
                with open(file_path, "r") as f:
                    content = f.read()
                    for line_num, line in enumerate(content.splitlines(), start=1):
                        for match in re.finditer(r"\$\((.*?)\)", line):
                            full_match = match.group(1)

                            version, index = full_match.split("-")
                            version = version.strip()
                            index = index.strip()
                            indexes = index.split("/")

                            for i in indexes:
                                matches.append(
                                    (file_path, line_num, version, i.strip())
                                )
            except UnicodeDecodeError:
                # Skip non-text files
                continue

    return matches


def run():
    if len(sys.argv) < 2:
        print("usage: python jambiato.py /path/to/your/code")
        return

    code_path = sys.argv[1]

    # Fetch releases
    latest = download_releases(META_DIR)

    # Create version db
    db = create_db(META_DIR)

    # Get all code tags
    tags = find_code_tags(code_path)

    def perc(v, tot=len(tags)):
        return int(100 * v / tot)

    print("Processing code...")

    outdated = []
    missing = []
    unrecognized = []

    implemented_versions = {}

    for t in tags:
        (file, line, version, index) = t

        if version != latest:
            outdated.append(t)

        if version not in implemented_versions:
            implemented_versions[version] = 0
        implemented_versions[version] += 1

        matches = list(filter(lambda x: x["index"] == index, db[version]))
        if len(matches) == 0:
            unrecognized.append(t)

    used_version = max(implemented_versions, key=implemented_versions.get)

    # Check for missing tags
    for t in db[latest]:
        matches = list(filter(lambda x: t["index"] == x[3], tags))
        if len(matches) == 0:
            missing.append(t)

    if len(missing) == 0 and len(outdated) == 0 and len(unrecognized) == 0:
        print("Your code is up to date")
        return

    print(
        f"\nYour codebase has {len(tags)} formula tags, latest version is {latest}, you are implementing {used_version}"
    )

    outdated.sort(key=lambda x: x[3])
    unrecognized.sort(key=lambda x: x[3])

    print(
        f"\nThere are {len(missing)} ({perc(len(missing), len(db[latest]))}%) missing definitions:",
        ", ".join(map(lambda t: f"{t['index']}", missing)),
    )

    print(
        f"\nThere are {len(outdated)} outdated tags ({perc(len(outdated))}%, latest is: {latest})"
    )
    outdated = sorted(
        outdated, key=lambda x: int(x[3])
    )  # Sort by formula index # f"{x[0]}{x[1]}")
    for t in outdated:
        (file, line, version, index) = t

        sout = (
            f"  {file+':'+str(line): <55}{version + ' - ' + index: <16}{'Outdated':<20}"
        )

        # Check for label matches
        matches = list(filter(lambda x: x["index"] == index, db[version]))
        label_match = False
        if len(matches) > 0 and matches[0]["label"] is not None:
            label = matches[0]["label"]
            matches_latest = list(filter(lambda x: x["label"] == label, db[latest]))
            if len(matches_latest) > 0:
                label_match = True
                if index != matches_latest[0]["index"]:
                    sout += f"{label}: {index} in {version} => becomes {matches_latest[0]['index']} in {latest}"
                if matches_latest[0]["tex"] != matches[0]["tex"]:
                    sout += " (content not equal between versions)"

        # Check for content matches
        if not label_match and len(matches) > 0:
            matches_latest = list(
                filter(lambda x: x["tex"] == matches[0]["tex"], db[latest])
            )
            if len(matches_latest) > 0:
                if index != matches_latest[0]["index"]:
                    sout += f"{index} in {version} => may became {matches_latest[0]['index']} in {latest} (content match)"

        print(sout)

    if len(unrecognized) > 0:
        print(
            f"\nThere are {len(unrecognized)} unrecognized tags ({perc(len(unrecognized))}%):"
        )
        for t in unrecognized:
            (file, line, version, index) = t
            print("\t", t)

    print(
        f"\nThe majority of equations implements version {used_version}; this is the version distribution:"
    )
    print(
        "\n".join(
            map(
                lambda x: f"  - {x[0]}: {x[1]} ({perc(x[1])}%)",
                implemented_versions.items(),
            )
        )
    )


if __name__ == "__main__":
    run()
