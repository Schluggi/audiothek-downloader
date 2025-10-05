import argparse
import json
import os
import re
import sys
from pathlib import Path

import requests
import yaml
from pathvalidate import sanitize_filename

API_URL = 'https://api.ardaudiothek.de/graphql'
GRAPHQL_DIR = os.path.join(Path(__file__).parent, 'graphql')
RENAME_TEMPLATES = os.path.join(Path(__file__).parent, 'rename_templates')


def rename(title: str, program_id: str, kind: str) -> str:
    template_path = os.path.join(RENAME_TEMPLATES, f'{program_id}.yaml')
    if os.path.isfile(template_path):
        with open(template_path, 'r') as f:
            template = yaml.safe_load(f)
        if template.get(kind):
            title = re.sub(template.get(kind).get('regex'), template.get(kind).get('substitution'), title)
    title = sanitize_filename(title)
    return title.strip()


def download_episodes(core_id: str, directory: str):
    url_type: str = args.url.lower().split(':')[3]

    match url_type:
        # case 'page':
        #     graphql_file = 'editorialCollection'
        case 'show':
            graphql_file = 'ProgramSetEpisodesQuery'
        case 'publication':
            graphql_file = 'episodesQuery'
        case _:
            exit(f'Error: URL type "{url_type}" is not supported')

    with open(os.path.join(GRAPHQL_DIR, f'{graphql_file}.graphql')) as f:
        query = f.read()

    response = requests.get(API_URL, params={
        'query': query,
        'variables': json.dumps({'coreId': core_id})
    })
    response_json: dict = response.json()

    if url_type == 'publication':
        nodes: list = [response_json.get('data').get('result')]
    else:
        nodes: list = response_json.get('data').get('result').get('items').get('nodes')

    for i, node in enumerate(nodes):
        show_id: str = node.get('programSet').get('id')
        item_title: str = node.get('title')

        filename: str = rename(item_title, show_id, 'fileTemplate')
        show_title: str = rename(node.get('programSet').get('title'), show_id, 'showTemplate')
        show_path: str = os.path.join(directory, show_title)

        if args.square_images:
            image_attr = 'url1X1'
        else:
            image_attr = 'url'
        
        title_image_url: str = node.get('image').get(image_attr).replace('{width}', '500')
        mp3_url: str = node.get('audios')[0].get('downloadUrl') or node.get('audios')[0].get('url')

        if args.group_episodes:
            episode_name = rename(item_title, show_id, 'episodeDirectoryTemplate')
            show_path: str = os.path.join(show_path, episode_name)

        if show_id:
            if not os.path.exists(show_path):
                try:
                    os.makedirs(show_path)
                except Exception as e:
                    print(f'[Error] Couldn\'t create output directory: {e}', file=sys.stderr)
                    continue

            image_file_path: str = os.path.join(show_path, f'{filename}.jpg')
            mp3_file_path: str = os.path.join(show_path, f'{filename}.mp3')

            if not os.path.exists(image_file_path):
                response_image = requests.get(title_image_url)
                with open(image_file_path, 'wb') as f:
                    f.write(response_image.content)

            print(f'Download: {i + 1} of {len(nodes)} -> {mp3_file_path}')

            if os.path.exists(mp3_file_path):
                print('skipping (file exists)')
            else:
                response_mp3 = requests.get(mp3_url)

                with open(mp3_file_path, 'wb') as f:
                    f.write(response_mp3.content)
        else:
            print('No show_id found!', file=sys.stderr)


if __name__ == '__main__':
    parser = argparse.ArgumentParser(
        description='ARD Audiothek downloader.'
    )
    parser.add_argument(
        '--url', '-u', type=str, default='', required=True,
        help='Insert audiothek url (e.g. https://www.ardaudiothek.de/sendung/2035-die-zukunft-beginnt-jetzt-scifi-mit-niklas-kolorz/12121989/)'
    )
    parser.add_argument(
        '--directory', '-f', type=str, default='output', help='directory to save all mp3s'
    )
    parser.add_argument('--square-images', '-s', action='store_true', default=False,
                        help='Download images in aspect ratio 1x1 instead of widescreen')
    parser.add_argument('--group-episodes', '-g', action='store_true', default=False,
                        help='Group episodes in own sub-directories')
    args = parser.parse_args()

    url_parser = re.search(r'(urn:ard:\w+:\w+)', args.url)
    if url_parser:
        download_episodes(url_parser.group(1), os.path.realpath(args.directory))
    else:
        exit('No ID found in URL')
