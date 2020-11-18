import numpy as np
import pandas as pd

# Test data download requirements:
import requests
import os
import hashlib

URL_DATA = "https://raw.githubusercontent.com/open2c/cooltools/pileup-update/datasets/external_test_files.tsv"


def assign_supports(features, supports, labels=False, suffix=""):
    """
    Assign support regions to a table of genomic intervals.

    Parameters
    ----------
    features : DataFrame
        Dataframe with columns `chrom`, `start`, `end`
        or `chrom1`, `start1`, `end1`, `chrom2`, `start2`, `end2`
    supports : array-like
        Support areas

    """
    features = features.copy()
    supp_col = pd.Series(index=features.index, data=np.nan)

    c = "chrom" + suffix
    s = "start" + suffix
    e = "end" + suffix
    for col in (c, s, e):
        if col not in features.columns:
            raise ValueError(
                'Column "{}" not found in features data frame.'.format(col)
            )

    for i, region in enumerate(supports):
        # single-region support
        if len(region) in [3, 4]:
            sel = (features[c] == region[0]) & (features[e] > region[1])
            if region[2] is not None:
                sel &= features[s] < region[2]
        # paired-region support
        elif len(region) == 2:
            region1, region2 = region
            sel1 = (features[c] == region1[0]) & (features[e] > region1[1])
            if region1[2] is not None:
                sel1 &= features[s] < region1[2]
            sel2 = (features[c] == region2[0]) & (features[e] > region2[1])
            if region2[2] is not None:
                sel2 &= features[s] < region2[2]
            sel = sel1 | sel2
        supp_col.loc[sel] = i

    if labels:
        supp_col = supp_col.map(lambda i: supports[int(i)], na_action="ignore")

    return supp_col


def assign_regions_to_bins(bin_ids, regions_span):
    regions_binsorted = (
        regions_span[(regions_span["bin_start"] >= 0) & (regions_span["bin_end"] >= 0)]
            .sort_values(["bin_start", "bin_end"])
            .reset_index()
    )

    bin_reg_idx_lo = regions_span["bin_start"].searchsorted(bin_ids, "right") - 1
    bin_reg_idx_hi = regions_span["bin_end"].searchsorted(bin_ids, "right")
    mask_assigned = (bin_reg_idx_lo == bin_reg_idx_hi) & (bin_reg_idx_lo >= 0)

    region_ids = pd.array([pd.NA] * len(bin_ids))
    region_ids[mask_assigned] = regions_span["name"][bin_reg_idx_lo[mask_assigned]]

    return region_ids


def download_file(url, local_filename=None):
    """
    Download single file and return its name.

    """

    if local_filename is None:
        local_filename = url.split('/')[-1]
    print('downloading:', url, 'as', local_filename)
    with requests.get(url, stream=True) as r:
        r.raise_for_status()
        with open(local_filename, 'wb') as f:
            for chunk in r.iter_content(chunk_size=8192):
                f.write(chunk)
    return local_filename


def download_data(name="all",
                  cache=True,
                  data_dir=None,
                  ignore_checksum=False,
                  checksum_chunk=8192,
                  _url_info=URL_DATA):
    """
    Download the specified dataset or all available datasets ("all" option).
    Check available datasets with cooltools.print_available_datasets()

    By default, checksums are verified for downloaded and cached files.

    Parameters
    ----------
    name : str
        Name of the dataset. Default: "all"

    cache : boolean, optional
        If True, try to load from the local cache first, and save to the cache
        if a download is required. Default: True

    data_dir : string, optional
        The directory where to cache data; default is defined by :func:`get_data_dir`.

    ignore_checksum : boolean, optional
        Ignore checksum of the file (not recommended). Default: False

    checksum_chunk : int, optional
        Sets the chunksize for calculation of md5sum of the file.
        Used only if ignore_checksum is False.

    Returns
    -------
    Path to the file if a single file was downloaded, or a list (for 'all' download).

    """

    available_datasets = _get_datasets_info(_url_info)
    available_keys = list(map(lambda x: x['key'], available_datasets))

    if name in available_keys:
        keys = [name]
    elif name == "all":
        keys = available_keys
    else:
        raise Exception(
            """Dataset {key} is not available. 
            Available datasets: {datasets}
            Use print_available_datasets() to see the details. 
            """.format(key=name, datasets=','.join(available_keys)))

    data_dir = get_data_dir(data_dir)

    assert len(keys) > 0  # Checking that test data file is parsed successfully
    downloaded = []
    for data in available_datasets:

        key, url, local_filename, original_checksum = data["key"], data["link"], data["filename"], data["checksum"]

        if key not in keys:
            continue

        file_path = os.path.join(data_dir, local_filename)

        if cache and os.path.exists(file_path):
            if not ignore_checksum:
                checksum = get_md5sum(file_path, chunksize=checksum_chunk)
                assert checksum==original_checksum, \
f"""The downloaded {key} file in {local_filename} differs from original test: {url}
Re-reun with cache=False """
            downloaded += [file_path]
            continue

        elif cache:
            print("Test dataset {} (file {}) is not in the cache directory {}".format(key, local_filename, data_dir))

        file_path = download_file(url, file_path)
        if not ignore_checksum:
            checksum = get_md5sum(file_path, chunksize=checksum_chunk)
            assert checksum == original_checksum, \
                f"Download of {key} to {local_filename} failed. File differs from original test: {url}"

        downloaded += [file_path]

    # No files, return empty string
    if len(downloaded) == 0:
        return ''
    # A single file downloaded, return its name
    elif len(downloaded) == 1:
        return downloaded[0]
    # Multiple files downloaded, return list
    else:
        return downloaded


def get_md5sum(file_path, chunksize=8192):
    """
    Load file by chunks and return md5sum of a file.
    File might be rather large, and we don't load it into memory as a whole.
    Name is excluded from calculation of hash.

    Parameters
    ----------
    file_path : str
        Location of the file

    chunksize : int
        Size of the chunk

    Returns
    -------
    String with md5sum hex hash

    """

    md5 = hashlib.md5()
    with open(file_path, "rb") as f:
        while True:
            file_fragment = f.read(chunksize)
            if not file_fragment:
                break
            md5.update(file_fragment)
        return md5.hexdigest()


def get_data_dir(data_dir=None):
    """
    Return a path to cache directory for example datasets.

    This directory is then used by :func:`download_data`.

    By default, this function uses the location of cooltools as the home folder
    and stores the files under ./datasets/ path there.

    Parameters
    ----------
    data_dir : str, optional
        Location of the home for test data storage

    Returns
    -------
    String with path to the folder with test data

    Notes
    -------
    Designed following seaborn download test data examples:
    https://github.com/mwaskom/seaborn/blob/4dd57d63e23e4628d8b7f41cdefdf64f7fefcf74/seaborn/utils.py#L427

    """

    if data_dir is None:
        data_dir = os.path.abspath(os.path.join(os.path.dirname(__file__), '..', '..', 'datasets/'))

    data_dir = os.path.expanduser(data_dir)
    if not os.path.exists(data_dir):
        os.makedirs(data_dir)

    return os.path.join(data_dir, '')


def _get_datasets_info(url=URL_DATA):
    """
    Reports all available datasets in URL_DATA

    Requires internet connection if url is a remote link.

    Returns
    -------

    A list of datasets, where each element is a dictionary with key, url, local_filename and checksum fields.

    """

    # Info file is remote
    if url.startswith("https://") or url.startswith("http://"):
        datasets_metadata = requests.get(url, stream=True).iter_lines()
    # Info file is local
    else:
        datasets_metadata = open(url, 'rb').readlines()

    header = []
    datasets_parsed = []
    for i, line_metadata in enumerate(datasets_metadata):
        # Read header:
        if line_metadata.decode("utf-8")[0] == "#":
            header = line_metadata.decode("utf-8")[2:].strip().split("\t")
        # Read the rest of the file:
        else:
            if len(header)==0:
                raise Exception(f"Data info file {url} is corrupted, no header denoted by '#'.")
            data_line = line_metadata.decode("utf-8").strip().split("\t")
            data = dict(zip(header, data_line))
            data.update({'index': i})
            datasets_parsed.append(dict(data))

    return datasets_parsed


def print_available_datasets(url=URL_DATA):
    """
    Prints all available test datasets in URL_DATA

    Requires internet connection if url is a remote link.

    """

    datasets_parsed = _get_datasets_info(url)
    for data in datasets_parsed:
        print("""{index}) {key} : {comment} 
\tDownloaded from {link} 
\tStored as {filename} 
\tOriginal md5sum: {checksum}
""".format(**data))
