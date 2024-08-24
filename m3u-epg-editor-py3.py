"""
This a python m3u / epg file optimizer script
This script enables download of m3u / epg files from a remote web server and introduces features to trim / optimize
these files to a set of wanted channel groups and channels along with the ability to sort / reorder channels

This can prove useful on underpowered devices where SPMC / KODI / some other app running on that device might struggle
to load a very large m3u / epg file

This script has been tested with:

1. vaderstreams m3u and epg files pulled from:
    http://<VADERSTREAMS_DOMAIN>/epg/vget?username=<USERNAME>&password=<PASSWORD>
    http://<VADERSTREAMS_DOMAIN>/p2.xml.gz

2. fab m3u and epg files pulled from:
    http://<FAB_DOMAIN>/get.php?username=<USERNAME>&password=<PASSWORD>&type=m3u_plus&output=ts
    http://<FAB_DOMAIN>/xmltv.php?username=<USERNAME>&password=<PASSWORD>

This script is intended for use with Python v3.x
"""

import sys
import os
import argparse
import json
import ast
import requests
import io
import re
import shutil
import gzip
from lxml.etree import Element, SubElement, parse, XMLParser
from xml.etree.ElementTree import tostring
import datetime
import dateutil.parser
import tzlocal
from urllib.request import url2pathname
from traceback import format_exception

log_enabled = False
log_items = []
start_timestamp = None


class M3uItem:
    def __init__(self, m3u_fields):
        self.tvg_name = None
        self.tvg_id = None
        self.tvg_logo = None
        self.group_title = None
        self.timeshift = None
        self.catchup_days = None
        self.catchup = None
        self.catchup_source = None
        self.name = None
        self.url = None
        self.group_idx = 0
        self.channel_idx = sys.maxsize

        if m3u_fields is not None:
            try:
                match = re.search('tvg-name="(.*?)"', m3u_fields, re.IGNORECASE)
                if match:
                    self.tvg_name = match.group(1)
                match = re.search('tvg-id="(.*?)"', m3u_fields, re.IGNORECASE)
                if match:
                    self.tvg_id = match.group(1)
                match = re.search('tvg-logo="(.*?)"', m3u_fields, re.IGNORECASE)
                if match:
                    self.tvg_logo = match.group(1)
                match = re.search('group-title="(.*?)"', m3u_fields, re.IGNORECASE)
                if match:
                    self.group_title = match.group(1)
                match = re.search('timeshift="(.*?)"', m3u_fields, re.IGNORECASE)
                if match:
                    self.timeshift = match.group(1)
                match = re.search('catchup-days="(.*?)"', m3u_fields, re.IGNORECASE)
                if match:
                    self.catchup_days = match.group(1)
                match = re.search('catchup="(.*?)"', m3u_fields, re.IGNORECASE)
                if match:
                    self.catchup = match.group(1)
                match = re.search('catchup-source="(.*?)"', m3u_fields, re.IGNORECASE)
                if match:
                    self.catchup_source = match.group(1)
                self.name = re.search('" ?,(.*)$', m3u_fields, re.IGNORECASE).group(1)
            except AttributeError as e:
                output_str("m3u file parse AttributeError: {0}".format(e))
            except Exception as ex:
                output_str("m3u file parse Exception: {0}".format(ex))

        if self.tvg_name is None or self.tvg_name == "":
            self.tvg_name = self.name

    def is_valid(self, allow_no_tvg_id):
        isvalid = self.tvg_name is not None and self.tvg_name != "" and \
                  self.group_title is not None and self.group_title != ""
        if not allow_no_tvg_id:
            isvalid = isvalid and self.tvg_id is not None and self.tvg_id != ""
        return isvalid


class FileUriAdapter(requests.adapters.BaseAdapter):

    @staticmethod
    def chk_path(method, path):
        # type: (object, object) -> object
        if method.lower() in ('put', 'delete'):
            return 501, "Not Implemented"
        elif method.lower() not in ('get', 'head'):
            return 405, "Method Not Allowed"
        elif os.path.isdir(path):
            return 400, "Path Not A File"
        elif not os.path.isfile(path):
            return 404, "File Not Found"
        elif not os.access(path, os.R_OK):
            return 403, "Access Denied"
        else:
            return 200, "OK"

    def send(self, req, **kwargs):
        path = os.path.normcase(os.path.normpath(url2pathname(req.path_url)))
        response = requests.Response()

        response.status_code, response.reason = self.chk_path(req.method, path)
        if response.status_code == 200 and req.method.lower() != 'head':
            try:
                is_gzipped = path.lower().endswith(".gz")
                if not is_gzipped:
                    response.raw = io.open(path, "rb")
                else:
                    response.raw = gzip.open(path, "rb")
            except (OSError, IOError) as err:
                response.status_code = 500
                response.reason = str(err)

        if isinstance(req.url, bytes):
            response.url = req.url.decode('utf-8')
        else:
            response.url = req.url

        response.request = req
        response.connection = self

        return response

    def close(self):
        pass


arg_parser = argparse.ArgumentParser(
    description='download and optimize m3u/epg files retrieved from a remote web server',
    formatter_class=argparse.ArgumentDefaultsHelpFormatter)
arg_parser.add_argument('--json_cfg', '-j', nargs='?',
                        help='A json input configuration file containing argument values.')
arg_parser.add_argument('--m3uurl', '-m', nargs='?', help='The url to pull the m3u file from. Both http:// and file:// protocols are supported.')
arg_parser.add_argument('--epgurl', '-e', nargs='?', help='The url to pull the epg file from. Both http:// and file:// protocols are supported.')
arg_parser.add_argument('--request_headers', '-rh', nargs='?', default=[],
                        help='An optional json array of key value pairs representing any required HTTP header values '
                             'to be sent in m3u and epg HTTP requests')
arg_parser.add_argument('--groups', '-g', nargs='?', help='Channel groups in the m3u to keep or discard. The default '
                                                          'mode is to keep the specified groups, switch to discard '
                                                          'mode with the -gm / --groupmode argument')
arg_parser.add_argument('--groupmode', '-gm', nargs='?', default='keep',
                        help='Specify "keep" or "discard" to control how the -g / --group argument should work. When '
                             'not specified, the -g / --group argument behaviour will default to keeping the '
                             'specified groups')
arg_parser.add_argument('--discard_channels', '-dc', nargs='?',
                        help='Channels in the m3u to discard. Regex pattern matching is supported')
arg_parser.add_argument('--include_channels', '-ic', nargs='?',
                        help='Channels in the m3u to keep. Regex pattern matching is supported. Channels matched in '
                             'this argument will always be kept, effectively overriding of any other group or channel '
                             'or url exclusion configuration.')
arg_parser.add_argument('--discard_urls', '-du', nargs='?',
                        help='Urls in the m3u to discard. Regex pattern matching is supported')
arg_parser.add_argument('--include_urls', '-iu', nargs='?',
                        help='Urls in the m3u to keep. Regex pattern matching is supported. Urls matched in '
                             'this argument will always be kept, effectively overriding of any other group or channel '
                             'or url exclusion configuration.')
arg_parser.add_argument('--id_transforms', '-it', nargs='?', default=[],
                        help='A json array of key value pairs representing source channel name values to target '
                             'tvg-id values to be transformed at processing time')
arg_parser.add_argument('--group_transforms', '-gt', nargs='?', default=[],
                        help='A json array of key value pairs representing source group names to target groups names '
                             'to be transformed at processing time')
arg_parser.add_argument('--channel_transforms', '-ct', nargs='?', default=[],
                        help='A json array of key value pairs representing source channel names to target channel names '
                             'to be transformed at processing time')
arg_parser.add_argument('--range', '-r', nargs='?', default=168,
                        help="An optional range window hours value used to validate programmes added to the newly generated epg xml")
arg_parser.add_argument('--sortchannels', '-s', nargs='?',
                        help='The optional desired sort order for channels in the generated m3u')
arg_parser.add_argument('--xml_sort_type', '-xs', nargs='?', default='none',
                        help='Specify "alpha" or "m3u" to control how channel elements within the resulting EPG xml '
                             'will be sorted. When not specified channel element sort order will follow the original '
                             'source xml sort order')
arg_parser.add_argument('--tvh_start', '-ts', nargs='?',
                        help='Optionally specify a start value to initialise the absolute start of numbering for '
                             'tvh-chnum attribute values')
arg_parser.add_argument('--tvh_offset', '-t', nargs='?',
                        help='An optional offset value applied to the Tvheadend tvh-chnum attribute within each '
                             'channel group')
arg_parser.add_argument('--no_tvg_id', '-nt', action='store_true',
                        help='Optionally allow channels with no tvg-id attribute to be considered as valid channels')
arg_parser.add_argument('--no_epg', '-ne', action='store_true',
                        help='Optionally prevent the download of and the creation of any EPG xml data')
arg_parser.add_argument('--force_epg', '-fe', action='store_true',
                        help='Works in tandem with no_tvg_id and no_epg. When EPG processing is enabled and when this '
                              'option is specified as true, the generated EPG file will be populated with elements for '
                              'channels in the m3u file that normally would have no EPG data')
arg_parser.add_argument('--no_sort', '-ns', action='store_true',
                        help='Optionally disable all channel sorting functionality')
arg_parser.add_argument('--http_for_images', '-hi', action='store_true',
                        help='Optionally prevent image attributes being populated where the source contains anything '
                             'other than a http url i.e. data:image uri content')
arg_parser.add_argument('--preserve_case', '-pc', action='store_true',
                        help='Optionally preserve the original case sensitivity of tvg-id and channel attributes as '
                             'supplied in the original M3U and EPG file data through to the target newly generated '
                             'M3U and EPG files')
arg_parser.add_argument('--outdirectory', '-d', nargs='?',
                        help='The output folder where retrieved and generated file are to be stored')
arg_parser.add_argument('--outfilename', '-f', nargs='?', help='The output filename for the generated files')
arg_parser.add_argument('--log_enabled', '-l', action='store_true', help='Optionally log script output to process.log')


# main entry point
def main():
    global start_timestamp
    start_timestamp = datetime.datetime.now()

    output_str("{0} process started with Python v{1}".format(os.path.basename(__file__), sys.version))
    args = validate_args()

    m3u_entries = load_m3u(args)
    m3u_entries = filter_m3u_entries(args, m3u_entries)

    if m3u_entries is not None and len(m3u_entries) > 0:
        if not args.no_sort:
            m3u_entries = sort_m3u_entries(args, m3u_entries)

        save_new_m3u(args, m3u_entries)

        if not args.no_epg:
            epg_filename = load_epg(args)
            if epg_filename is not None:
                xml_tree = create_new_epg(args, epg_filename, m3u_entries)
                if xml_tree is not None:
                    save_new_epg(args, xml_tree)

    save_log(args)


# creates a dictionary from the supplied list_items
def create_dictionary(list_items):
    dictionary = {}
    for item in list_items:
        dictionary_key = next(iter(item.keys()))
        dictionary_value = next(iter(item.values()))
        dictionary[dictionary_key] = dictionary_value
    return dictionary


# parses and validates cli arguments passed to this script
def validate_args():
    global log_enabled
    args = arg_parser.parse_args()

    output_str("input script arguments: {0}".format(str(args)))

    if args.json_cfg:
        args = hydrate_args_from_json(args, args.json_cfg)

    if not args.m3uurl:
        abort_process('--m3uurl is mandatory', 1, args)

    if not args.no_epg and not args.epgurl:
        abort_process('--epgurl is mandatory', 1, args)

    if not args.groups:
        abort_process('--groups is mandatory', 1, args)

    if not args.json_cfg:
        if args.request_headers:
            args.request_headers = create_dictionary(json.loads(args.request_headers)["request_headers"])
        else:
            args.request_headers = {}

        set_str = '([' + args.groups + '])'
        args.group_idx = list(ast.literal_eval(set_str))
        args.groups = set(ast.literal_eval(set_str))

        if args.discard_channels:
            set_str = '([' + args.discard_channels + '])'
            args.discard_channels = list(ast.literal_eval(set_str))
        else:
            args.discard_channels = list()

        if args.include_channels:
            set_str = '([' + args.include_channels + '])'
            args.include_channels = list(ast.literal_eval(set_str))
        else:
            args.include_channels = list()

        if args.discard_urls:
            set_str = '([' + args.discard_urls + '])'
            args.discard_urls = list(ast.literal_eval(set_str))
        else:
            args.discard_urls = list()

        if args.include_urls:
            set_str = '([' + args.include_urls + '])'
            args.include_urls = list(ast.literal_eval(set_str))
        else:
            args.include_urls = list()

        if args.id_transforms:
            args.id_transforms = json.loads(args.id_transforms)["id_transforms"]

        if args.group_transforms:
            args.group_transforms = json.loads(args.group_transforms)["group_transforms"]

        if args.channel_transforms:
            args.channel_transforms = json.loads(args.channel_transforms)["channel_transforms"]

        if args.range:
            args.range = int(args.range)

        if args.sortchannels:
            list_str = '([' + args.sortchannels + '])'
            args.sortchannels = list(ast.literal_eval(list_str))
        else:
            args.sortchannels = []

        if args.tvh_start:
            args.tvh_start = int(args.tvh_start) - 1
        else:
            args.tvh_start = 0

        if args.tvh_offset:
            args.tvh_offset = int(args.tvh_offset)
        else:
            args.tvh_offset = 0

        log_enabled = args.log_enabled

    if not args.outdirectory:
        abort_process('--outdirectory is mandatory', 1, args)

    out_directory = os.path.expanduser(args.outdirectory)
    if not os.path.exists(out_directory):
        abort_process(out_directory + ' does not exist in your filesystem', 1, args)
    elif not os.path.isdir(out_directory):
        abort_process(out_directory + ' is not a folder in your filesystem', 1, args)

    if not args.outfilename:
        abort_process('--outfilename is mandatory', 1, args)

    output_str("determined runtime script arguments: {0}".format(str(args)))

    return args


# hydrates the runtime args from the json file described by json_cfg_file_path
def hydrate_args_from_json(args, json_cfg_file_path):
    global log_enabled
    with open(json_cfg_file_path) as json_cfg_file:

        json_str = json_cfg_file.read().replace('\n', '').replace('    ', '')
        output_str("json configuration: {0}".format(json_str))

        json_data = json.loads(json_str)

        if "request_headers" in json_data:
            args.request_headers = create_dictionary(json_data["request_headers"])
        else:
            args.request_headers = {}

        if "no_epg" in json_data:
            args.no_epg = json_data["no_epg"]

        if not "m3uurl" in json_data:
            abort_process('m3uurl is mandatory', 1, args)

        if not args.no_epg and not "epgurl" in json_data:
            abort_process('epgurl is mandatory', 1, args)

        args.m3uurl = json_data["m3uurl"]

        if not args.no_epg:
            args.epgurl = json_data["epgurl"]

        args.group_idx = json_data["groups"]
        args.groups = set(args.group_idx)

        if "groupmode" in json_data:
            args.groupmode = (json_data["groupmode"])

        if "discard_channels" in json_data:
            args.discard_channels = json_data["discard_channels"]
        else:
            args.discard_channels = list()

        if not type(args.discard_channels) is list:
            abort_process('discard_channels is expected to be a json array in {}'.format(json_cfg_file_path), 1, args)

        if "include_channels" in json_data:
            args.include_channels = json_data["include_channels"]
        else:
            args.include_channels = list()

        if not type(args.include_channels) is list:
            abort_process('include_channels is expected to be a json array in {}'.format(json_cfg_file_path), 1, args)

        if "discard_urls" in json_data:
            args.discard_urls = json_data["discard_urls"]
        else:
            args.discard_urls = list()

        if not type(args.discard_urls) is list:
            abort_process('discard_urls is expected to be a json array in {}'.format(json_cfg_file_path), 1, args)

        if "include_urls" in json_data:
            args.include_urls = json_data["include_urls"]
        else:
            args.include_urls = list()

        if not type(args.include_urls) is list:
            abort_process('include_urls is expected to be a json array in {}'.format(json_cfg_file_path), 1, args)

        if "id_transforms" in json_data:
            args.id_transforms = json_data["id_transforms"]
        else:
            args.id_transforms = []

        if "group_transforms" in json_data:
            args.group_transforms = json_data["group_transforms"]
        else:
            args.group_transforms = []

        if "channel_transforms" in json_data:
            args.channel_transforms = json_data["channel_transforms"]
        else:
            args.channel_transforms = []

        if "range" in json_data:
            args.range = json_data["range"]

        if "sortchannels" in json_data:
            args.sortchannels = json_data["sortchannels"]
        else:
            args.sortchannels = []

        if not type(args.sortchannels) is list:
            abort_process('sortchannels is expected to be a json array in {}'.format(json_cfg_file_path), 1, args)

        if "xml_sort_type" in json_data:
            args.xml_sort_type = json_data["xml_sort_type"]

        if "tvh_start" in json_data:
            args.tvh_start = json_data["tvh_start"]
        else:
            args.tvh_start = 0

        if "tvh_offset" in json_data:
            args.tvh_offset = json_data["tvh_offset"] - 1
        else:
            args.tvh_offset = 0

        if "no_tvg_id" in json_data:
            args.no_tvg_id = json_data["no_tvg_id"]
        if "force_epg" in json_data:
            args.force_epg = json_data["force_epg"]
        if "no_sort" in json_data:
            args.no_sort = json_data["no_sort"]
        if "http_for_images" in json_data:
            args.http_for_images = json_data["http_for_images"]
        if "preserve_case" in json_data:
            args.preserve_case = json_data["preserve_case"]

        if "outdirectory" in json_data:
            args.outdirectory = json_data["outdirectory"]

        if "outfilename" in json_data:
            args.outfilename = json_data["outfilename"]

        if "log_enabled" in json_data:
            log_enabled = json_data["log_enabled"]

    return args


# global exception handler
def handle_exception(exc_type, exc_value, exc_traceback):
    ex_lines = format_exception(exc_type, exc_value, exc_traceback)
    output_str(''.join(ex_lines))
    abort_process('process terminated early due to an exception', 2, None)


# runtime exception handler wire up
sys.excepthook = handle_exception


# controlled script abort mechanism
def abort_process(reason, exitcode, args):
    output_str(reason)
    save_log(args)
    sys.exit(exitcode)


# helper print function with timestamp
def output_str(event_str):
    global log_items
    try:
        log_item = u"%s %s" % (datetime.datetime.now().isoformat(), event_str)
        print(log_item)
        log_items.append(log_item.strip())
        return log_item.strip()
    except IOError as e:
        if e.errno != 0:
            print("I/O error({e.errno}): {e.strerror} for event string '{event_str}'")


# saves the runtime log (if enabled)
def save_log(args):
    global log_enabled
    global log_items
    global start_timestamp

    if log_enabled:
        if args is not None and args.outdirectory is not None:
            out_dir = args.outdirectory
        else:
            out_dir = os.path.dirname(os.path.realpath(__file__))

        log_target = os.path.join(out_dir, "process.log")
        output_str("saving to log: " + log_target)
        with io.open(log_target, "w", encoding="utf-8") as log_file:
            for log_item in log_items:
                log_file.write(u"{0}\n".format(log_item))

            runtime = datetime.datetime.now() - start_timestamp
            minutes = (runtime.seconds % 3600) // 60
            seconds = runtime.seconds % 60
            log_str = output_str("script runtime: %s minutes %s seconds" % (minutes, seconds))
            log_file.write(u"{0}\n".format(log_str))

            log_str = output_str("process completed")
            log_file.write(u"{0}\n".format(log_str))
    else:
        output_str("process completed")


########################################################################################################################
# m3u functions
########################################################################################################################
# downloads an m3u, converts it to a list and returns it
def load_m3u(args):
    m3u_response = get_m3u(args.m3uurl, args.request_headers)
    if m3u_response.status_code == 200:
        m3u_filename = save_original_m3u(args.outdirectory, m3u_response)
        if args.m3uurl.lower().startswith('http'):
            m3u_response.close()
        m3u_entries = parse_m3u(m3u_filename, args)
        return m3u_entries
    else:
        output_str("the HTTP GET request to {} returned status code {}".format(args.m3uurl, m3u_response.status_code))
        m3u_response.close()


# performs the HTTP: or FILE: GET
def get_m3u(m3u_url, request_headers):
    output_str("performing HTTP GET request to " + m3u_url)

    if m3u_url.lower().startswith('file'):
        session = requests.session()
        session.mount('file://', FileUriAdapter())
        response = session.get(m3u_url)
    else:
        response = requests.get(m3u_url, headers=request_headers)

    return response


# saves the HTTP GET response to the file system
def save_original_m3u(out_directory, m3u_response):
    m3u_target = os.path.join(out_directory, "original.m3u8")
    output_str("saving retrieved m3u file: " + m3u_target)
    with io.open(m3u_target, "wb") as m3u_file:
        m3u_file.write(m3u_response.content)
        return m3u_target


# parses the m3u file represented by m3u_filename into a list of M3uItem objects and returns them
def parse_m3u(m3u_filename, args):
    m3u_entries = []
    output_str("parsing m3u into a list of objects")

    with io.open(m3u_filename, "r", encoding="utf-8") as m3u_file:
        line = m3u_file.readline()

        if "#EXTM3U" not in line:
            output_str("{} doesn't start with #EXTM3U, it doesn't appear to be an M3U file".format(m3u_filename))
            return m3u_entries

        entry = M3uItem(None)
        file_line_idx = 1
        try:
            for line in m3u_file:
                line = line.strip()
                if line.startswith('#EXTINF:'):
                    m3u_fields = line.split('#EXTINF:0 ')[1] if line.startswith('#EXTINF:0') else line.split('#EXTINF:-1 ')[1]
                    entry = M3uItem(m3u_fields)
                elif len(line) != 0:
                    entry.url = line
                    if M3uItem.is_valid(entry, args.no_tvg_id):
                        m3u_entries.append(entry)
                    entry = M3uItem(None)
                file_line_idx += 1
        except Exception as ex:
            output_str("m3u file read exception on line {0} : {1}".format(file_line_idx, ex))

    output_str("m3u contains {} items".format(len(m3u_entries)))
    return m3u_entries


# transforms the given string_value using the supplied transforms list of dictionary items
def transform_string_value(string_value, compare_value, transforms):
    for transform_item in transforms:
        src_value = next(iter(transform_item.keys()))
        replacement_value = next(iter(transform_item.values()))
        if compare_value is not None:
            if compare_value == src_value:
                string_value = replacement_value
        elif src_value in string_value:
            string_value = string_value.replace(src_value, replacement_value)
        else:
            string_value = re.sub(src_value, replacement_value, string_value)
    return string_value


# filters the given m3u_entries using the supplied groups
def filter_m3u_entries(args, m3u_entries):
    filtered_m3u_entries = []
    if m3u_entries is not None and len(m3u_entries) > 0:
        keeping_discarding = "keeping" if args.groupmode == "keep" else "discarding"
        output_str("{} channel groups in this list {}".format(keeping_discarding, str(args.group_idx)))
        if len(args.discard_channels) > 0:
            output_str("ignoring channels in this list {}".format(str(args.discard_channels)))
        if len(args.include_channels) > 0:
            output_str("hard keeping channels in this list {}".format(str(args.include_channels)))
        if len(args.discard_urls) > 0:
            output_str("ignoring urls in this list {}".format(str(args.discard_urls)))
        if len(args.include_urls) > 0:
            output_str("hard keeping urls in this list {}".format(str(args.include_urls)))

        if not args.no_sort:
            # sort the channels by name by default
            m3u_entries = sorted(m3u_entries, key=lambda entry: entry.tvg_name)

        all_channels_name_target = os.path.join(args.outdirectory, "original.channels.txt")
        with io.open(all_channels_name_target, "w", encoding="utf-8") as all_channels_file:
            for m3u_entry in m3u_entries:
                all_channels_file.write("\"%s\",\"%s\"\n" % (m3u_entry.tvg_name, m3u_entry.group_title))
                group_matched = is_item_matched(args.groups, m3u_entry.group_title)

                # check whether the given group is wanted based on the groupmode argument value (defaults to "keep")
                group_included = False
                if args.groupmode == "keep":
                    group_included = group_matched
                elif args.groupmode == "discard":
                    group_included = not group_matched

                channel_discarded = is_item_matched(args.discard_channels, m3u_entry.tvg_name)
                channel_always_kept = is_item_matched(args.include_channels, m3u_entry.tvg_name)
                url_discarded = is_item_matched(args.discard_urls, m3u_entry.url)
                url_always_kept = is_item_matched(args.include_urls, m3u_entry.url)
                always_kept = channel_always_kept or url_always_kept

                if (group_included and not channel_discarded and not url_discarded) or always_kept:
                    m3u_entry.tvg_id = transform_string_value(m3u_entry.tvg_id, m3u_entry.tvg_name, args.id_transforms)
                    m3u_entry.group_title = transform_string_value(m3u_entry.group_title, None, args.group_transforms)
                    m3u_entry.tvg_name = transform_string_value(m3u_entry.tvg_name, None, args.channel_transforms)
                    m3u_entry.name = transform_string_value(m3u_entry.name, None, args.channel_transforms)
                    filtered_m3u_entries.append(m3u_entry)

        output_str("filtered m3u contains {} items".format(len(filtered_m3u_entries)))
    return filtered_m3u_entries


# returns an indicator that describes whether the given item_name is matched in the given item_list
def is_item_matched(item_list, item_name):
    matched = False
    if len(item_list) > 0:
        # try an exact match
        matched = item_name in item_list

        if not matched:
            # try a regex match against all groups
            matched = any(re.search(regex_str, item_name, re.IGNORECASE) for regex_str in item_list)

    return matched


# sorts the given m3u_entries using the supplied args.groups and args.sortchannels
def sort_m3u_entries(args, m3u_entries):
    idx = 0
    for group_title in args.group_idx:
        idx += 1
        for m3u_item in m3u_entries:
            if m3u_item.group_title == group_title:
                m3u_item.group_idx = idx

    if len(args.sortchannels) > 0:
        idx = 0
        for sort_channel in args.sortchannels:
            m3u_item = next((x for x in m3u_entries if x.tvg_name.lower() == sort_channel.lower()), None)
            if m3u_item is not None:
                m3u_item.channel_idx = idx
            idx += 1

        # a specific sort channel order is specified so sort the entries by group and the specified channel order
        output_str("desired channel sort order: {}, {}".format(str(args.group_idx), str(args.sortchannels)))
        m3u_entries = sorted(m3u_entries, key=lambda entry: (entry.group_idx, entry.channel_idx))
    else:
        # no specific sort channel order is specified so sort the entries by group and channel name
        output_str("sorting filtered items alphabetically by group and channel name")
        m3u_entries = sorted(m3u_entries, key=lambda entry: (entry.group_title, entry.tvg_name))

    return m3u_entries


# saves the given m3u_entries into the file system
def save_new_m3u(args, m3u_entries):
    if m3u_entries is not None:
        idx = args.tvh_start
        m3u_target = os.path.join(args.outdirectory, args.outfilename + ".m3u8")
        filtered_channels_name_target = os.path.join(args.outdirectory, args.outfilename + ".channels.txt")
        output_str("saving new m3u file: " + m3u_target)

        with io.open(m3u_target, "w", encoding="utf-8") as m3u_target_file:
            with io.open(filtered_channels_name_target, "w", encoding="utf-8") as filtered_channels_file:

                m3u_target_file.write("%s\n" % u"#EXTM3U")
                group_title = m3u_entries[0].group_title

                for entry in m3u_entries:

                    meta = "#EXTINF:-1"

                    if args.http_for_images and entry.tvg_logo is not None:
                        logo = entry.tvg_logo if entry.tvg_logo.startswith("http") else ""
                    else:
                        logo = entry.tvg_logo

                    if args.tvh_start > 0 or args.tvh_offset > 0:
                        if entry.group_title == group_title:
                            idx += 1
                        else:
                            group_title = entry.group_title
                            floor = (idx // args.tvh_offset)
                            idx = args.tvh_offset * (floor + 1)
                            idx += 1

                        meta += ' tvh-chnum="%s"' % idx

                    if entry.tvg_id is not None:
                        channel_id = entry.tvg_id.lower() if not args.preserve_case else entry.tvg_id
                        meta += ' tvg-id="%s"' % channel_id

                    meta += ' tvg-name="%s"' % entry.tvg_name

                    if logo is not None:
                        meta += ' tvg-logo="%s"' % logo

                    if entry.group_title is not None:
                        meta += ' group-title="%s"' % entry.group_title

                    if entry.timeshift is not None:
                        meta += ' timeshift="%s"' % entry.timeshift

                    if entry.catchup_days is not None:
                        meta += ' catchup-days="%s"' % entry.catchup_days

                    if entry.catchup is not None:
                        meta += ' catchup="%s"' % entry.catchup

                    if entry.catchup_source is not None:
                        meta += ' catchup-source="%s"' % entry.catchup_source

                    meta += ",%s\n" % entry.name

                    m3u_target_file.write(meta)
                    m3u_target_file.write('%s\n' % entry.url)
                    filtered_channels_file.write(
                        "\"%s\",\"%s\"\n" % (entry.tvg_name, entry.group_title))


########################################################################################################################
# epg functions
########################################################################################################################
# downloads an epg gzip file, saves it, extracts it and returns the path to the extracted epg xml
def load_epg(args):
    epg_response = get_epg(args.epgurl, args.request_headers)
    if epg_response.status_code == 200:
        is_gzipped = \
            args.epgurl.lower().endswith(".gz") or \
            ("content-type" in epg_response.headers and epg_response.headers["content-type"] == "application/x-gzip")
        is_http_response = args.epgurl.lower().startswith("http")
        epg_filename = save_original_epg(is_gzipped, is_http_response, args.outdirectory, epg_response)
        if is_http_response:
            epg_response.close()
        if is_gzipped:
            epg_filename = extract_original_epg(args.outdirectory, epg_filename)
        return epg_filename
    else:
        output_str("the HTTP GET request to {} returned status code {}".format(args.epgurl, epg_response.status_code))
        epg_response.close()


# performs the HTTP: or FILE: GET
def get_epg(epg_url, request_headers):
    output_str("performing HTTP GET request to " + epg_url)

    if epg_url.lower().startswith('file'):
        session = requests.session()
        session.mount('file://', FileUriAdapter())
        response = session.get(epg_url)
    else:
        response = requests.get(epg_url, headers=request_headers, stream=True)

    return response


# saves the http / file GET response to the file system
def save_original_epg(is_gzipped, is_http_response, out_directory, epg_response):
    epg_target = os.path.join(out_directory, "original.gz" if is_gzipped else "original.xml")
    output_str("saving retrieved epg file: " + epg_target)

    with io.open(epg_target, "wb") if not isinstance(epg_response.raw, gzip.GzipFile) else gzip.open(epg_target,
                                                                                                  "wb") as epg_file:

        if not isinstance(epg_response.raw, gzip.GzipFile):
            if is_http_response:
                epg_response.raw.decode_content = True
                shutil.copyfileobj(epg_response.raw, epg_file)
            else:
                epg_file.write(epg_response.content)
        else:
            epg_file.write(epg_response.content)

    return epg_target


# extracts the given epg_filename and saves it to the file system
def extract_original_epg(out_directory, epg_filename):
    epg_target = os.path.join(out_directory, "original.xml")
    output_str("extracting retrieved epg file to: " + epg_target)
    with gzip.open(epg_filename, 'rb') as f_in, open(epg_target, 'wb') as f_out:
        shutil.copyfileobj(f_in, f_out)
        return epg_target


# pretty prints the xml document represented by root_elem
def indent(root_elem, level=0):
    i = "\n" + level * "  "
    if len(root_elem):
        if not root_elem.text or not root_elem.text.strip():
            root_elem.text = i + "  "
        if not root_elem.tail or not root_elem.tail.strip():
            root_elem.tail = i
        for root_elem in root_elem:
            indent(root_elem, level + 1)
        if not root_elem.tail or not root_elem.tail.strip():
            root_elem.tail = i
    else:
        if level and (not root_elem.tail or not root_elem.tail.strip()):
            root_elem.tail = i


# returns an indicator whether the given timestamp in within the configured range window
def is_in_range(args, timestamp):
    now = datetime.datetime.now(timestamp.tzinfo)
    range_start = now - datetime.timedelta(hours=args.range)
    range_end = now + datetime.timedelta(hours=args.range)
    return range_start <= timestamp <= range_end


# creates a new epg from the epg represented by original_epg_filename using the given m3u_entries as a template
def create_new_epg(args, original_epg_filename, m3u_entries):
    tvg_id_unique_entries = {e.tvg_id.lower(): e for e in m3u_entries}.values()
    output_str("creating new xml epg for {} m3u items".format(len(tvg_id_unique_entries)))
    try:
        xml_parser = XMLParser(recover=True)
        original_tree = parse(original_epg_filename, xml_parser)
        original_root = original_tree.getroot()

        if original_root is None:
            output_str("epg creation failure, the supplied source {0} epg file appears to have no root element. Check the source data.".format(original_epg_filename))
            return None

        new_root = Element("tv")
        new_root.set("source-info-name", "m3u-epg-editor")
        new_root.set("source-info-url", "github.com/bebo-dot-dev/m3u-epg-editor")
        new_root.set("source-data-url", "github.com/bebo-dot-dev/m3u-epg-editor")
        new_root.set("generator-info-name", "m3u-epg-editor")
        new_root.set("generator-info-url", "https://github.com/bebo-dot-dev/m3u-epg-editor")

        # create a channel element for every channel present in the m3u
        epg_channel_count = 0
        created_channels = []
        for channel in original_root.iter('channel'):
            channel_id = channel.get("id")
            channel_created = any(u == channel_id for u in created_channels)
            if channel_id is not None and channel_id != "" and \
                    not channel_created and \
                    any(x.tvg_id.lower() == channel_id.lower() for x in tvg_id_unique_entries):
                output_str("creating channel element for {}".format(channel_id))
                epg_channel_count += 1
                new_channel = SubElement(new_root, "channel")
                new_channel.set("id", channel_id.lower() if not args.preserve_case else channel_id)
                for elem in channel:
                    new_elem = SubElement(new_channel, elem.tag)
                    elem_text = elem.text
                    if new_elem.tag.lower() == "display-name":
                        elem_text = transform_string_value(elem_text, None, args.channel_transforms)
                    new_elem.text = elem_text
                    for attr_key in elem.keys():
                        attr_val = elem.get(attr_key)
                        if elem.tag.lower() == "icon" and args.http_for_images:
                            attr_val = attr_val if attr_val.startswith("http") else ""
                        new_elem.set(attr_key, attr_val)
                created_channels.append(channel_id)

        if args.no_tvg_id and args.force_epg:
            # create a channel element for every channel present in the m3u where there is no tvg_id and where there is a tvg_name value
            for entry in m3u_entries:
                if entry.tvg_id is None or entry.tvg_id == "" or entry.tvg_id == "None":
                    output_str("creating channel element for m3u entry from tvg-name value {}".format(entry.tvg_name))
                    epg_channel_count += 1
                    new_channel = SubElement(new_root, "channel")
                    new_channel.set("id", entry.tvg_name)
                    new_elem = SubElement(new_channel, "display-name")
                    new_elem.text = entry.tvg_name

        if epg_channel_count > 0:
            # perform any specified channel element sorting
            if args.xml_sort_type == 'alpha':
                channels = new_root.findall("channel[@id]")
                alpha_sorted_channels = sorted(channels, key=lambda ch_elem: (ch_elem.tag, ch_elem.get('id')))
                new_root[:] = alpha_sorted_channels
            elif args.xml_sort_type == 'm3u':
                channels = new_root.findall("channel[@id]")
                m3u_sorted_channels = sorted(channels, key=lambda
                    ch_elem: (ch_elem.tag, [x.tvg_id.lower() for x in tvg_id_unique_entries].index(ch_elem.get('id').lower())))
                new_root[:] = m3u_sorted_channels

            all_epg_programmes_xpath = 'programme'
            all_epg_programmes = original_tree.findall(all_epg_programmes_xpath)
            if len(all_epg_programmes) > 0 and not args.preserve_case:
                # force the channel (tvg-id) attribute value to lowercase to enable a case-insensitive
                # xpath lookup with: channel_xpath = 'programme[@channel="' + entry.tvg_id.lower() + '"]'
                for programme in all_epg_programmes:
                    for attr_key in programme.keys():
                        attr_val = programme.get(attr_key)
                        if attr_key.lower() == 'channel' and attr_val is not None:
                            programme.set(attr_key, attr_val.lower())

        # create a dictionary of all channels in the EPG to enable fast searching
        channel_dictionary = create_channel_dictionary(original_root)

        # now copy all programme elements from the original epg for every channel present in the m3u
        no_epg_channels = []
        max_programme_start_timestamp = datetime.datetime.now(tzlocal.get_localzone()) - datetime.timedelta(days=365 * 10)
        programme_count = 0
        for entry in tvg_id_unique_entries:
            if entry.tvg_id is not None and entry.tvg_id != "" and entry.tvg_id != "None":
                output_str("creating programme elements for {}".format(entry.tvg_name))
                # dictionary search
                channel_name = entry.tvg_id.lower() if not args.preserve_case else entry.tvg_id
                if channel_name in channel_dictionary:
                    channel_programmes = channel_dictionary[channel_name]
                    for elem in channel_programmes:
                        programme_start_timestamp = dateutil.parser.parse(elem.get("start"))
                        max_programme_start_timestamp = programme_start_timestamp if programme_start_timestamp > max_programme_start_timestamp else max_programme_start_timestamp
                        if is_in_range(args, programme_start_timestamp):
                            programme_count += 1
                            programme = SubElement(new_root, elem.tag)
                            for attr_key in elem.keys():
                                attr_val = elem.get(attr_key)
                                programme.set(attr_key, attr_val)
                            for sub_elem in elem:
                                new_elem = SubElement(programme, sub_elem.tag)
                                new_elem.text = sub_elem.text
                                for attr_key in sub_elem.keys():
                                    attr_val = sub_elem.get(attr_key)
                                    new_elem.set(attr_key, attr_val)
                                for sub_sub_elem in sub_elem:
                                    new_sub_elem = SubElement(new_elem, sub_sub_elem.tag)
                                    new_sub_elem.text = sub_sub_elem.text
                                    for attr_key in sub_sub_elem.keys():
                                        attr_val = sub_sub_elem.get(attr_key)
                                        new_sub_elem.set(attr_key, attr_val)
                else:
                    if not args.no_tvg_id or not args.force_epg:
                        no_epg_channels.append(entry)
            else:
                if not args.no_tvg_id or not args.force_epg:
                    no_epg_channels.append(entry)

        if args.no_tvg_id and args.force_epg:
            # create programme elements for every channel present in the m3u where there is no tvg_id and where there is a tvg_name value
            for entry in m3u_entries:
                if entry.tvg_id is None or entry.tvg_id == "" or entry.tvg_id == "None":
                    output_str("creating pseudo programme elements for m3u entry {}".format(entry.tvg_name))
                    programme_start_timestamp = datetime.datetime.now(tzlocal.get_localzone())
                    programme_stop_timestamp = programme_start_timestamp + datetime.timedelta(hours=2)
                    max_programme_start_timestamp = max_programme_start_timestamp if programme_start_timestamp > max_programme_start_timestamp else programme_start_timestamp
                    for i in range(1, 168):  # create programme elements within a max 7 day window and no more limited by the configured range
                        if is_in_range(args, programme_start_timestamp):
                            programme_count += 1
                            programme = SubElement(new_root, "programme")
                            programme.set("start", programme_start_timestamp.strftime("%Y%m%d%H0000 %z"))
                            programme.set("stop", programme_stop_timestamp.strftime("%Y%m%d%H0000 %z"))
                            programme.set("channel", entry.tvg_name)
                            title_elem = SubElement(programme, "title")
                            title_elem.text = entry.tvg_name
                            desc_elem = SubElement(programme, "desc")
                            desc_elem.text = entry.tvg_name
                            programme_start_timestamp = programme_start_timestamp + datetime.timedelta(hours=2)
                            programme_stop_timestamp = programme_stop_timestamp + datetime.timedelta(hours=2)

        now = datetime.datetime.now(tzlocal.get_localzone())
        range_start = now - datetime.timedelta(hours=args.range)
        range_end = now + datetime.timedelta(hours=args.range)
        output_str('configured epg programme start/stop range is +/-{0}hrs from now ({1} <-> {2})'.format(
            args.range, range_start.strftime("%d %b %Y %H:%M"), range_end.strftime("%d %b %Y %H:%M")))
        output_str('latest programme start timestamp found was: {0}'.format(max_programme_start_timestamp.strftime("%d %b %Y %H:%M")))
        output_str('{0} programmes were added to the epg'.format(programme_count))

        if len(no_epg_channels) > 0:
            save_no_epg_channels(args, no_epg_channels)

        indent(new_root)
        return new_root
    except Exception as e:
        # likely a mangled xml parse exception
        output_str("epg creation failure: {0}".format(e))
        return None


# creates a dictionary of channels from the supplied EPG root node
def create_channel_dictionary(epg_root):
    channel_dict = {}

    for element in epg_root.iterchildren():

        tag = element.tag.split('}')[1] if '}' in element.tag else element.tag

        if tag == 'programme':
            key = element.get('channel')
        else:
            continue

        if key in channel_dict:
            channel_dict[key].append(element)
        else:
            channel_dict[key] = [element]

    return channel_dict


# saves the no_epg_channels list into the file system
def save_no_epg_channels(args, no_epg_channels):
    no_epg_channels_target = os.path.join(args.outdirectory, "no_epg_channels.txt")
    with io.open(no_epg_channels_target, "w", encoding="utf-8") as no_epg_channels_file:
        for m3u_entry in no_epg_channels:
            no_epg_channels_file.write("\"%s\",\"%s\"\n" % (m3u_entry.tvg_name, m3u_entry.tvg_id))


# saves the epg xml document represented by epg_xml into the file system
def save_new_epg(args, epg_xml):
    epg_xml_str = ('<?xml version="1.0" encoding="UTF-8"?>' + '\n' +
                   '<!DOCTYPE tv SYSTEM "xmltv.dtd">' + '\n' +
                   tostring(epg_xml, encoding="unicode"))

    epg_target = os.path.join(args.outdirectory, args.outfilename + ".xml")
    output_str("saving new epg xml file: " + epg_target)
    with io.open(epg_target, "w", encoding="utf-8") as epg_xml_file:
        epg_xml_file.write(epg_xml_str)


if __name__ == '__main__':
    main()
