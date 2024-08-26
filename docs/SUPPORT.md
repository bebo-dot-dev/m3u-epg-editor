# m3u-epg-editor bugs
Due to the nature of how the python script in this project works to read input data and transform received input data into new resulting output files, issues are often related to the input data processed and the arguments passed to the script to process input data.

Script input arguments can become misaligned to input data and changing input data and/or input data quality can be the cause of issues that arise.

In the event of a bug issue being raised for support of somethng not working as expected, the following *must* be supplied in the bug issue report:

1. **All** input arguments passed to the script CLI / **complete** input `--json_cfg` configuration attached.
2. A sample input m3u data file and an epg data file (if in use) attached. These are the unmodified original data files that the script processes as desribed by `--m3uurl` and `--epgurl`
3. The `--log_enabled` log file of a run where the problem occurred attached.

Please supply sanitised data files with username/passwords removed and attach the smallest files possible that reliably reproduce the issue.
