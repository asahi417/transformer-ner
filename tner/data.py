""" Fetch/format NER dataset
TODO: allow using multiple custom path and preset data + custom path
"""
import os
import zipfile
import logging
import re
import requests
import tarfile
import shutil
from typing import Dict, List
from itertools import chain
from tqdm import tqdm
from .japanese_tokenizer import SudachiWrapper

STOPWORDS = ['None', '#']
panx_language_list = [
    "ace", "bg", "da", "fur", "ilo", "lij", "mzn", "qu", "su", "vi", "af", "bh", "de", "fy", "io", "lmo", "nap",
    "rm", "sv", "vls", "als", "bn", "diq", "ga", "is", "ln", "nds", "ro", "sw", "vo", "am", "bo", "dv", "gan", "it",
    "lt", "ne", "ru", "szl", "wa", "an", "br", "el", "gd", "ja", "lv", "nl", "rw", "ta", "war", "ang", "bs", "eml",
    "gl", "jbo", "map-bms", "nn", "sa", "te", "wuu", "ar", "ca", "en", "gn", "jv", "mg", "no", "sah", "tg", "xmf",
    "arc", "cbk-zam", "eo", "gu", "ka", "mhr", "nov", "scn", "th", "yi", "arz", "cdo", "es", "hak", "kk", "mi",
    "oc", "sco", "tk", "yo", "as", "ce", "et", "he", "km", "min", "or", "sd", "tl", "zea", "ast", "ceb", "eu", "hi",
    "kn", "mk", "os", "sh", "tr", "zh-classical", "ay", "ckb", "ext", "hr", "ko", "ml", "pa", "si", "tt",
    "zh-min-nan", "az", "co", "fa", "hsb", "ksh", "mn", "pdc", "simple", "ug", "zh-yue", "ba", "crh", "fi", "hu",
    "ku", "mr", "pl", "sk", "uk", "zh", "bar", "cs", "fiu-vro", "hy", "ky", "ms", "pms", "sl", "ur", "bat-smg",
    "csb", "fo", "ia", "la", "mt", "pnb", "so", "uz", "be-x-old", "cv", "fr", "id", "lb", "mwl", "ps", "sq", "vec",
    "be", "cy", "frr", "ig", "li", "my", "pt", "sr", "vep"
]
VALID_DATASET = ['conll2003', 'wnut2017', 'ontonotes5', 'mit_movie_trivia', 'mit_restaurant', 'fin', 'bionlp2004',
                 'bc5cdr'] + ['panx_dataset_{}'.format(i) for i in panx_language_list]  # 'wiki_ja', 'wiki_news_ja'
CACHE_DIR = '{}/.cache/tner'.format(os.path.expanduser('~'))

# Shared label set across different dataset
SHARED_NER_LABEL = {
    "location": ["LOCATION", "LOC", "location", "Location"],
    "organization": ["ORGANIZATION", "ORG", "organization"],
    "person": ["PERSON", "PSN", "person", "PER"],
    "date": ["DATE", "DAT", 'YEAR', 'Year'],
    "time": ["TIME", "TIM", "Hours"],
    "artifact": ["ARTIFACT", "ART", "artifact"],
    "percent": ["PERCENT", "PNT"],
    "other": ["OTHER", "MISC"],
    "money": ["MONEY", "MNY", "Price"],
    "corporation": ["corporation", "CORP"],  # Wnut 17
    "group": ["group", "NORP", "GRP"],
    "product": ["product", "PRODUCT", "PROD"],
    "rating": ["Rating", 'RATING'],  # restaurant review
    "amenity": ["Amenity"],
    "restaurant": ["Restaurant_Name"],
    "dish": ["Dish"],
    "cuisine": ["Cuisine"],
    "actor": ['ACTOR', 'Actor'],  # movie review
    "title": ['TITLE'],
    "genre": ['GENRE', 'Genre'],
    "director": ['DIRECTOR', 'Director'],
    "song": ['SONG'],
    "plot": ['PLOT', 'Plot'],
    "review": ['REVIEW'],
    'character': ['CHARACTER'],
    "ratings average": ['RATINGS_AVERAGE'],
    'trailer': ['TRAILER'],
    'opinion': ['Opinion'],
    'award': ['Award'],
    'origin': ['Origin'],
    'soundtrack': ['Soundtrack'],
    'relationship': ['Relationship'],
    'character name': ['Character_Name'],
    'quote': ['Quote'],
    "cardinal number": ["CARDINAL"],  # OntoNote 5
    "ordinal number": ["ORDINAL"],
    "quantity": ['QUANTITY'],
    "law": ['LAW'],
    "geopolitical area": ['GPE'],
    "work of art": ["WORK_OF_ART", "work-of-art", "creative-work", "CW", 'creative'],
    "facility": ["FAC"],
    "language": ["LANGUAGE"],
    "event": ["EVENT"],
    "dna": ["DNA"],  # bionlp2004
    "protein": ["protein"],
    "cell type": ["cell_type"],
    "cell line": ["cell_line"],
    "rna": ["RNA"],
    "chemical": ["Chemical"],  # bc5cdr
    "disease": ["Disease"]
}

__all__ = ("get_dataset", "VALID_DATASET", "SHARED_NER_LABEL", "CACHE_DIR", "panx_language_list", "decode_file")


def open_compressed_file(url, cache_dir):
    path = wget(url, cache_dir)
    if path.endswith('.tar.gz') or path.endswith('.tgz'):
        tar = tarfile.open(path, "r:gz")
        tar.extractall(cache_dir)
        tar.close()
    elif path.endswith('.zip'):
        with zipfile.ZipFile(path, 'r') as zip_ref:
            zip_ref.extractall(cache_dir)


def wget(url, cache_dir):
    filename = os.path.basename(url)
    try:
        with open('{}/{}'.format(cache_dir, filename), "wb") as f:

            r = requests.get(url)
            f.write(r.content)
    except requests.exceptions.ConnectionError:
        os.remove('{}/{}'.format(cache_dir, filename))
        raise requests.exceptions.ConnectionError()
    return '{}/{}'.format(cache_dir, filename)


def get_dataset(data: (List, str) = None,
                custom_data: Dict = None,
                label_to_id: Dict = None,
                fix_label_dict: bool = False,
                lower_case: bool = False,
                keep_original_surface: bool = False):
    """ Fetch NER dataset

     Parameter
    -----------------
    data_names: list
        A list of dataset name
        eg) 'panx_dataset/*', 'conll2003', 'wnut2017', 'ontonote5', 'mit_movie_trivia', 'mit_restaurant'
    custom_data_path: str
        Filepath to custom dataset
    custom_data_language: str
        Language for custom_data_path dataset
    label_to_id: dict
        A dictionary of label to id
    fix_label_dict: bool
        Fixing given label_to_id dictionary (ignore label not in the dictionary in dataset)
    lower_case: bool
        Converting data into lowercased

     Return
    ----------------
    unified_data: dict
        A dataset consisting of 'train'/'valid' (only 'train' if more than one data set is used)
    label_to_id: dict
        A dictionary of label to id
    language: str
        Most frequent language in the dataset
    """
    assert data is not None or custom_data is not None

    if data is not None:
        data = data if data is not None else []
        data_list = [data] if type(data) is str else data
        logging.info('target dataset: {}'.format(data_list))
        data = []
        languages = []
        unseen_entity_set = {}
        for d in data_list:
            data_split_all, label_to_id, language, ues = get_dataset_single(
                d, label_to_id=label_to_id, fix_label_dict=fix_label_dict, lower_case=lower_case)
            data.append(data_split_all)
            languages.append(language)
            unseen_entity_set = ues if len(unseen_entity_set) == 0 else unseen_entity_set.intersection(ues)
        if len(data) > 1:
            unified_data = {
                'train': {
                    'data': list(chain(*[d['train']['data'] for d in data])),
                    'label': list(chain(*[d['train']['label'] for d in data]))
                }
            }
            # use the most frequent language in the data
            freq = list(map(lambda x: (x, len(list(filter(lambda y: y == x, languages)))), set(languages)))
            language = sorted(freq, key=lambda x: x[1], reverse=True)[0][0]
        else:
            unified_data = data[0]
    else:
        unified_data, label_to_id, language, unseen_entity_set = get_dataset_single(
            label_to_id=label_to_id,
            fix_label_dict=fix_label_dict,
            lower_case=lower_case,
            custom_data=custom_data,
            keep_original_surface=keep_original_surface)

    return unified_data, label_to_id, language, unseen_entity_set


def get_dataset_single(data_name: str = None,
                       custom_data: Dict = None,
                       label_to_id: Dict = None,
                       fix_label_dict: bool = False,
                       lower_case: bool = False,
                       allow_new_entity: bool = True,
                       cache_dir: str = None,
                       keep_original_surface: bool = False):
    """ download dataset file and return dictionary including training/validation split

    :param data_name: data set name or path to the data
    :param label_to_id: fixed dictionary of (label: id). If given, ignore other labels
    :param fix_label_dict: not augment label_to_id based on dataset if True
    :param lower_case: convert to lower case
    :param custom_data: dictionary with 'train'/'test'/'valid'/'language'
    :param allow_new_entity
    :return: formatted data, label_to_id
    """
    post_process_ja = False
    entity_first = False
    to_bio = False
    language = 'en'
    cache_dir = cache_dir if cache_dir is not None else CACHE_DIR
    os.makedirs(cache_dir, exist_ok=True)
    if data_name is not None:
        data_path = os.path.join(cache_dir, data_name)
        logging.info('data_name: {}'.format(data_name))
        logging.info('loading preset data: {}'.format(data_name))
        if data_name in ['ontonotes5', 'conll2003']:

            files_info = {'train': 'train.txt', 'valid': 'dev.txt', 'test': 'test.txt'}
            if not os.path.exists(data_path):
                os.makedirs(data_path, exist_ok=True)
                # raise ValueError('please download Ontonotes5 from https://catalog.ldc.upenn.edu/LDC2013T19')
                url = 'https://github.com/asahi417/neighbor-tagging/raw/master/data.tar.gz'
                open_compressed_file(url, data_path)
                for i in ['train', 'dev', 'test']:
                    if data_name == 'ontonotes5':
                        conll_formatting(
                            file_token='{}/data/onto/{}.words'.format(data_path, i),
                            file_tag='{}/data/onto/{}.ner'.format(data_path, i),
                            output_file='{}/{}.txt'.format(data_path, i))
                    else:
                        conll_formatting(
                            file_token='{}/data/conll2003/conll2003-{}.words'.format(data_path, i),
                            file_tag='{}/data/conll2003/conll2003-{}.nertags'.format(data_path, i),
                            output_file='{}/{}.txt'.format(data_path, i))
        elif data_name == 'bc5cdr':
            files_info = {'train': 'train.txt', 'valid': 'dev.txt', 'test': 'test.txt'}
            if not os.path.exists(data_path):
                os.makedirs(data_path, exist_ok=True)
                url = 'https://github.com/JHnlp/BioCreative-V-CDR-Corpus/raw/master/CDR_Data.zip'
                open_compressed_file(url, data_path)
                shutil.move('{}/CDR_Data/CDR.Corpus.v010516'.format(data_path), data_path)

            def __process_single(_r):
                title, body = _r.split('\n')[:2]
                entities = _r.split('\n')[2:]
                text = title.split('|t|')[-1] + ' ' + body.split('|a|')[-1]
                _tokens = []
                _tags = []
                last_end = 0
                for e in entities:
                    start, end = e.split('\t')[1:3]
                    try:
                        start, end = int(start), int(end)
                    except ValueError:
                        continue
                    mention = e.split('\t')[3]
                    entity_type = e.split('\t')[4]
                    assert text[start:end] == mention
                    _tokens_tmp = list(filter(
                        lambda _x: len(_x) > 0, map(lambda m: m.replace(' ', ''), re.split(r'\b', text[last_end:start]))
                    ))
                    last_end = end
                    _tokens += _tokens_tmp
                    _tags += ['O'] * len(_tokens_tmp)
                    _mention_token = mention.split(' ')
                    _tokens += _mention_token
                    _tags += ['B-{}'.format(entity_type)] + ['I-{}'.format(entity_type)] * (len(_mention_token) - 1)
                    assert len(_tokens) == len(_tags)
                return _tokens, _tags

            def convert_to_iob(path, export):
                path = '{0}/{1}'.format(data_path, path)
                with open(path, 'r') as f:
                    raw = list(filter(lambda _x: len(_x) > 0, f.read().split('\n\n')))
                    token_tag = list(map(lambda _x: __process_single(_x), raw))
                    tokens, tags = list(zip(*token_tag))
                    conll_formatting(tokens=tokens, tags=tags, output_file=os.path.join(data_path, export), sentence_division='.')

            convert_to_iob('CDR.Corpus.v010516/CDR_DevelopmentSet.PubTator.txt', 'dev.txt')
            convert_to_iob('CDR.Corpus.v010516/CDR_TestSet.PubTator.txt', 'test.txt')
            convert_to_iob('CDR.Corpus.v010516/CDR_TrainingSet.PubTator.txt', 'train.txt')
        elif data_name == 'bionlp2004':  # https://www.aclweb.org/anthology/W04-1213.pdf
            files_info = {'train': 'Genia4ERtask1.iob2', 'valid': 'Genia4EReval1.iob2'}
            if not os.path.exists(data_path):
                os.makedirs(data_path, exist_ok=True)
                url = 'http://www.nactem.ac.uk/GENIA/current/Shared-tasks/JNLPBA/Train/Genia4ERtraining.tar.gz'
                open_compressed_file(url, data_path)
                url = 'http://www.nactem.ac.uk/GENIA/current/Shared-tasks/JNLPBA/Evaluation/Genia4ERtest.tar.gz'
                open_compressed_file(url, data_path)
        elif data_name == 'fin':  # https://www.aclweb.org/anthology/U15-1010.pdf
            files_info = {'train': 'FIN5.txt', 'valid': 'FIN3.txt'}
            if not os.path.exists(data_path):
                os.makedirs(data_path, exist_ok=True)
                url = 'https://people.eng.unimelb.edu.au/tbaldwin/resources/finance-sec/financial_risk_assessment.tgz'
                open_compressed_file(url, data_path)
                for v in files_info.values():
                    shutil.move('{}/dataset/{}'.format(data_path, v), data_path)
            to_bio = True
        elif data_name == 'mit_restaurant':
            files_info = {'train': 'restauranttrain.bio', 'valid': 'restauranttest.bio'}
            if not os.path.exists(data_path):
                os.makedirs(data_path, exist_ok=True)
                url = 'https://groups.csail.mit.edu/sls/downloads/restaurant/restauranttrain.bio'
                open_compressed_file(url, data_path)
                url = 'https://groups.csail.mit.edu/sls/downloads/restaurant/restauranttest.bio'
                open_compressed_file(url, data_path)
            entity_first = True
        elif data_name == 'mit_movie_trivia':
            files_info = {'train': 'trivia10k13train.bio', 'valid': 'trivia10k13test.bio'}
            if not os.path.exists(data_path):
                os.makedirs(data_path, exist_ok=True)
                url = 'https://groups.csail.mit.edu/sls/downloads/movie/trivia10k13train.bio'
                open_compressed_file(url, data_path)
                url = 'https://groups.csail.mit.edu/sls/downloads/movie/trivia10k13test.bio'
                open_compressed_file(url, data_path)
            entity_first = True
        elif data_name == 'wnut2017':
            files_info = {'train': 'train.txt', 'valid': 'valid.txt', 'test': 'test.txt'}
            if not os.path.exists(data_path):
                os.makedirs(data_path, exist_ok=True)
                url = 'https://github.com/leondz/emerging_entities_17/raw/master/wnut17train.conll'
                open_compressed_file(url, data_path)
                with open('{}/wnut17train.conll'.format(data_path), 'r') as f:
                    with open('{}/train.txt'.format(data_path), 'w') as f_w:
                        f_w.write(f.read().replace('\t', ' '))

                url = 'https://github.com/leondz/emerging_entities_17/raw/master/emerging.dev.conll'
                open_compressed_file(url, data_path)
                with open('{}/emerging.dev.conll'.format(data_path), 'r') as f:
                    with open('{}/valid.txt'.format(data_path), 'w') as f_w:
                        f_w.write(f.read().replace('\t', ' '))

                url = 'https://raw.githubusercontent.com/leondz/emerging_entities_17/master/emerging.test.annotated'
                open_compressed_file(url, data_path)
                with open('{}/emerging.test.annotated'.format(data_path), 'r') as f:
                    with open('{}/test.txt'.format(data_path), 'w') as f_w:
                        f_w.write(f.read().replace('\t', ' '))
        elif 'panx_dataset' in data_name:
            files_info = {'valid': 'dev.txt', 'train': 'train.txt', 'test': 'test.txt'}
            panx_la = data_name.replace('/', '_').split('_')[-1]
            if not os.path.exists(data_path):
                os.makedirs(data_path, exist_ok=True)
                url = 'https://github.com/asahi417/neighbor-tagging/releases/download/0.0.0/wikiann.zip'
                open_compressed_file(url, cache_dir)
                tar = tarfile.open('{0}/panx_dataset/{1}.tar.gz'.format(cache_dir, panx_la), "r:gz")
                tar.extractall(data_path)
                tar.close()
                for v in files_info.values():
                    os.system("sed -e 's/{0}://g' {1}/{2} > {1}/{2}.txt".format(panx_la, data_path, v.replace('.txt', '')))
                    os.system("rm -rf {0}/{1}".format(data_path, v.replace('.txt', '')))
            if panx_la == 'ja':
                language = 'ja'
                post_process_ja = True
        else:
            raise ValueError('unknown data: {}'.format(data_name))
    else:
        logging.info('loading custom data: {}'.format(custom_data))
        if 'language' in custom_data:
            language = custom_data.pop('language')
        # assert 'train' in custom_data, 'Training set not found, make sure you include `train` in the custom data.'
        # assert 'valid' in custom_data, 'Validation set not found, make sure you include `valid` in the custom data.'
        for k, v in custom_data.items():
            logging.info('formatting custom dataset from {}'.format(v))
            if not os.path.exists(v):
                raise ValueError('not found custom file: {}'.format(v))
        files_info = custom_data
        data_path = None
    label_to_id = dict() if label_to_id is None else label_to_id
    data_split_all, unseen_entity_set, label_to_id = decode_all_files(
        files_info, data_path=data_path, label_to_id=label_to_id, fix_label_dict=fix_label_dict, entity_first=entity_first,
        to_bio=to_bio, allow_new_entity=allow_new_entity, keep_original_surface=keep_original_surface)

    if post_process_ja:
        logging.info('Japanese tokenization post processing')
        id_to_label = {v: k for k, v in label_to_id.items()}
        label_fixer = SudachiWrapper()
        data, label = [], []
        for k, v in data_split_all.items():
            for x, y in tqdm(zip(v['data'], v['label'])):
                y = [id_to_label[_y] for _y in y]
                _data, _label = label_fixer.fix_ja_labels(inputs=x, labels=y)
                _label = [label_to_id[_y] for _y in _label]
                data.append(_data)
                label.append(_label)
            v['data'] = data
            v['label'] = label

    if lower_case:
        logging.info('convert into lower cased')
        data_split_all = {
            k: {'data': [[ii.lower() for ii in i] for i in v['data']], 'label': v['label']}
            for k, v in data_split_all.items()}
    return data_split_all, label_to_id, language, unseen_entity_set


def decode_file(file_name: str,
                data_path: str = None,
                label_to_id: Dict = None,
                fix_label_dict: bool = False,
                entity_first: bool = False,
                to_bio: bool = False,
                allow_new_entity: bool = False,
                keep_original_surface: bool = False):
    inputs, labels, seen_entity, dates = [], [], [], []
    label_to_id = {} if label_to_id is None else label_to_id
    past_mention = 'O'
    if data_path is not None:
        file_name = os.path.join(data_path, file_name)
    with open(file_name, 'r') as f:
        sentence, entity = [], []
        for n, line in enumerate(f):
            line = line.strip()

            # MultiCoNER has header
            if line.startswith('# id '):
                continue

            if line.startswith('# "id":'):
                date = line.split('"created_at": ')[-1].replace('"', '')
                dates.append(date)
                continue

            if len(line) == 0 or line.startswith("-DOCSTART-"):
                if len(sentence) != 0:
                    assert len(sentence) == len(entity)
                    inputs.append(sentence)
                    labels.append(entity)
                    sentence, entity = [], []
            else:
                ls = line.split(' ')
                # MultiCoNER separate token and tag by 'in _ _ O' so need to ignore '_'
                ls = [i for i in ls if i != '_']
                if len(ls) < 2:
                    continue
                # Examples could have no label for mode = "test"
                if entity_first:
                    tag, word = ls[0], ls[1:-1]
                else:
                    word, tag = ls[0:-1], ls[-1]
                word = ' '.join(word)
                if tag == 'junk':
                    continue
                if word in STOPWORDS:
                    continue
                sentence.append(word)

                # convert tag into unified label set
                if tag != 'O':  # map tag by custom dictionary
                    mention = '-'.join(tag.split('-')[1:])
                    if not keep_original_surface:
                        location = tag.split('-')[0]

                        if to_bio and mention == past_mention:
                            location = 'I'
                        elif to_bio:
                            location = 'B'
                        fixed_mention = [k for k, v in SHARED_NER_LABEL.items() if mention in v]

                        if len(fixed_mention) == 0 and allow_new_entity:
                            tag = '-'.join([location, mention])
                        elif len(fixed_mention) == 0:
                            tag = 'O'
                        else:
                            tag = '-'.join([location, fixed_mention[0]])
                    past_mention = mention
                else:
                    past_mention = 'O'

                # if label dict is fixed, unknown tag type will be ignored
                if tag not in label_to_id.keys() and fix_label_dict:
                    tag = 'O'
                elif tag not in label_to_id.keys() and not fix_label_dict:
                    label_to_id[tag] = len(label_to_id)

                entity.append(label_to_id[tag])

    id_to_label = {v: k for k, v in label_to_id.items()}
    unseen_entity_id = set(label_to_id.values()) - set(list(chain(*labels)))
    unseen_entity_label = {id_to_label[i] for i in unseen_entity_id}
    if len(dates) > 0:
        assert len(dates) == len(labels) == len(inputs)
        return label_to_id, unseen_entity_label, {"data": inputs, "label": labels, "date": dates}
    else:
        return label_to_id, unseen_entity_label, {"data": inputs, "label": labels}


def decode_all_files(files: Dict,
                     label_to_id: Dict,
                     fix_label_dict: bool,
                     data_path: str = None,
                     entity_first: bool = False,
                     to_bio: bool = False,
                     allow_new_entity: bool = False,
                     keep_original_surface: bool = False):
    data_split = dict()
    unseen_entity = None
    for name, filepath in files.items():
        label_to_id, unseen_entity_set, data_dict = decode_file(
            filepath, data_path=data_path, label_to_id=label_to_id, fix_label_dict=fix_label_dict,
            entity_first=entity_first, to_bio=to_bio, allow_new_entity=allow_new_entity,
            keep_original_surface=keep_original_surface)
        if unseen_entity is None:
            unseen_entity = unseen_entity_set
        else:
            unseen_entity = unseen_entity.intersection(unseen_entity_set)
        data_split[name] = data_dict
        if data_path is not None:
            logging.info('dataset {0}/{1}: {2} entries'.format(data_path, filepath, len(data_dict['data'])))
        else:
            logging.info('dataset {0}: {1} entries'.format(filepath, len(data_dict['data'])))
    return data_split, unseen_entity, label_to_id


def conll_formatting(output_file: str,
                     file_token: str=None,
                     file_tag: str=None,
                     tokens=None,
                     tags=None,
                     sentence_division=None):
    """ convert a separate ner/token file into single ner Conll 2003 format """
    if file_token:
        with open(file_token, 'r') as f:
            tokens = [i.split(' ') for i in f.read().split('\n')]
    if file_tag:
        with open(file_tag, 'r') as f:
            tags = [i.split(' ') for i in f.read().split('\n')]
    assert tokens and tags
    _end = False
    with open(output_file, 'w') as f:
        assert len(tokens) == len(tags)
        for _token, _tag in zip(tokens, tags):
            assert len(_token) == len(_tag)
            for __token, __tag in zip(_token, _tag):
                _end = False
                f.write('{0} {1}\n'.format(__token, __tag))
                if sentence_division and __token == sentence_division:
                    f.write('\n')
                    _end = True
            if _end:
                _end = False
            else:
                f.write('\n')
                _end = True

