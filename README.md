# m3u-epg-editor
An m3u / epg file optimizer script written in python

m3u-epg-editor enables download of m3u / epg files from a remote web server and introduces features to trim / optimize
these files to a set of wanted channel groups along with the ability to sort / reorder channels

These features might be useful on underpowered devices where SPMC/KODI/some other app running on that device might struggle
to download and process a large m3u / epg file. It might also be useful simply where an improved sort order of channels is required

This script has been **tested with vaderstreams** m3u and epg files pulled from:

1. [http://api.vaders.tv/vget?username=[USERNAME]&password=[PASSWORD]&format=ts](http://api.vaders.tv/vget?username=[USERNAME]&password=[PASSWORD]&format=ts) (m3u file)
2. [http://vaders.tv/p2.xml.gz](http://vaders.tv/p2.xml.gz) (epg file)

   It is worth highlighting that vaderstreams do support filtering of their m3u in the HTTP GET request/response via the `filterCategory` query string parameter i.e. the following request will remove all of the specified filterCategory groups in the returned m3u response:

   [http://api.vaders.tv/vget?username=[USERNAME]&password=[PASSWORD]&filterCategory=Afghani,Arabic,Bangla,Canada,Filipino,France,Germany,Gujrati,India,Ireland,Italy,Latino,Live%20Events,Malayalam,Marathi,Pakistan,Portugal,Punjabi,Spain,Tamil,United%20States,United%20States%20Regionals&format=ts](http://api.vaders.tv/vget?username=[USERNAME]&password=[PASSWORD]&filterCategory=Afghani,Arabic,Bangla,Canada,Filipino,France,Germany,Gujrati,India,Ireland,Italy,Latino,Live%20Events,Malayalam,Marathi,Pakistan,Portugal,Punjabi,Spain,Tamil,United%20States,United%20States%20Regionals&format=ts)

However there are some things where there is no obvious, easy or indeed completely free solution:

1. vaderstreams does provide any method to remove specific channels within categories / groups
2. vaderstreams does provide any method to re-order / sort channels within categories / groups to achieve a desired custom sort order
3. vaderstreams does provide any method to reduce the volume of data within the epg to include only those channels that are required
4. vaderstreams does provide any method to reduce the time window of data within the epg

m3u-epg-editor solves these problems

***

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

***

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
                        An optional range window (in hours) to consider when adding programmes to the epg
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

***

#### files created by this script:

![files](https://github.com/jjssoftware/m3u-epg-editor/blob/master/screenshots/files-screenshot-2018-01-20-10.03.28.png)

Each time this script is run, the following files will be created / overwritten in the specified `--outdirectory / -d` path:

* **original.m3u**

   This is the original unmodified m3u file downloaded from the specified `--m3uurl / -m` remote server
   
* **original.gz**

   This is the original unmodified epg gzip file downloaded from the specified `--epgurl / -e` remote server
   
* **original.xml**

   This is the original unmodified epg xml file extracted from the original epg gzip file 
   
* **[--outfilename].m3u**

   This is the new rewritten m3u file created from the original m3u file. This will contain all of the channels that you've decided to keep. Channels are optionally sorted according to the sort order specified in `--sortchannels / -s`
   
* **[--outfilename].channels.txt**

   This is basically a raw text file log containing the list of channel names from the original m3u that you've decided to keep. This can be useful for constructing a desired `--sortchannels / -s` sort order.
   
* **[--outfilename].xml**

   This is the new rewritten epg file created from the original epg file that contains epg data for all of the channels that you've decided to keep. If `--range / -r` was specified, epg data will be filtered to only include entries that fall within the range window of `range_start <= programme_start <= range_end`
   
* **no_epg_channels.txt**

   This is a log of any channels that you decided to keep that were subsequently found to have no epg data available. This can be useful to help to construct a list of `--channels / -c` channels to exclude if i.e. you only want to keep those channels where epg data is available
