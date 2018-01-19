# m3u-epg-editor
This a python m3u / epg file optimizer script

It implements a method to download m3u / epg files from a remote web server and to "trim" or optimize
these files to a set of wanted channel groups

This can be useful on underpowered devices where SPMC/KODI/some other app running on that device might struggle
to load a very large m3u / epg file

This script has been **tested with vaderstreams m3u and epg files** pulled from:

    http://api.vaders.tv/vget?username=<USERNAME>&password=<PASSWORD>&format=ts
    http://vaders.tv/p2.xml.gz
    
#### dependencies:
`python`

#### python modules used by this script:
```
import sys
import os
import argparse
import ast
import requests
import re
import shutil
import gzip
from xml.etree.cElementTree import Element, SubElement, parse, ElementTree
import datetime
import dateutil.parser
```

#### command line options:
```
$ python ./m3u-epg-editor.py --help
usage: m3u-epg-editor.py [-h] [--m3uurl [M3UURL]] [--epgurl [EPGURL]]
                         [--groups [GROUPS]] [--channels [CHANNELS]]
                         [--range [RANGE]] [--sortchannels [SORTCHANNELS]]
                         [--outdirectory [OUTDIRECTORY]]
                         [--outfilename [OUTFILENAME]]

download and optimize m3u/epg files retrieved from a remote web server

optional arguments:
  -h, --help            show this help message and exit
  --m3uurl [M3UURL], -m [M3UURL]
                        The url to pull the m3u file from
  --epgurl [EPGURL], -e [EPGURL]
                        The url to pull the epg file from
  --groups [GROUPS], -g [GROUPS]
                        Channel groups in the m3u to keep
  --channels [CHANNELS], -c [CHANNELS]
                        Individual channels in the m3u to discard
  --range [RANGE], -r [RANGE]
                        An optional range window to consider when adding programmes to the epg
  --sortchannels [SORTCHANNELS], -s [SORTCHANNELS]
                        The optional desired sort order for channels in the generated m3u
  --outdirectory [OUTDIRECTORY], -d [OUTDIRECTORY]
                        The output folder where retrieved and generated file are to be stored
  --outfilename [OUTFILENAME], -f [OUTFILENAME]
                        The output filename for the generated files
```

#### sample usage call:
```
$ python ./m3u-epg-editor.py -m="http://api.vaders.tv/vget?username=<USERNAME>&password=<PASSWORD>&format=ts" -e="http://vaders.tv/p2.xml.gz" -g="'sports','premium movies'" -c="'willow hd','bein sports espanol hd'" -r=12 -d="/home/target_directory" -f="output_file"
```
