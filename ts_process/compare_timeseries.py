#!/usr/bin/env python3
"""
BSD 3-Clause License

Copyright (c) 2018, Southern California Earthquake Center
All rights reserved.

Redistribution and use in source and binary forms, with or without
modification, are permitted provided that the following conditions are met:

* Redistributions of source code must retain the above copyright notice, this
  list of conditions and the following disclaimer.

* Redistributions in binary form must reproduce the above copyright notice,
  this list of conditions and the following disclaimer in the documentation
  and/or other materials provided with the distribution.

* Neither the name of the copyright holder nor the names of its
  contributors may be used to endorse or promote products derived from
  this software without specific prior written permission.

THIS SOFTWARE IS PROVIDED BY THE COPYRIGHT HOLDERS AND CONTRIBUTORS "AS IS"
AND ANY EXPRESS OR IMPLIED WARRANTIES, INCLUDING, BUT NOT LIMITED TO, THE
IMPLIED WARRANTIES OF MERCHANTABILITY AND FITNESS FOR A PARTICULAR PURPOSE ARE
DISCLAIMED. IN NO EVENT SHALL THE COPYRIGHT HOLDER OR CONTRIBUTORS BE LIABLE
FOR ANY DIRECT, INDIRECT, INCIDENTAL, SPECIAL, EXEMPLARY, OR CONSEQUENTIAL
DAMAGES (INCLUDING, BUT NOT LIMITED TO, PROCUREMENT OF SUBSTITUTE GOODS OR
SERVICES; LOSS OF USE, DATA, OR PROFITS; OR BUSINESS INTERRUPTION) HOWEVER
CAUSED AND ON ANY THEORY OF LIABILITY, WHETHER IN CONTRACT, STRICT LIABILITY,
OR TORT (INCLUDING NEGLIGENCE OR OTHERWISE) ARISING IN ANY WAY OUT OF THE USE
OF THIS SOFTWARE, EVEN IF ADVISED OF THE POSSIBILITY OF SUCH DAMAGE.

The program is to plot a simple comparison among timeseries files
"""
from __future__ import division, print_function

# Import Python modules
import os
import argparse
import matplotlib as mpl
if mpl.get_backend() != 'agg':
    mpl.use('Agg') # Disables use of Tk/X11
from file_utilities import read_file
from ts_library import calculate_distance, filter_timeseries
from ts_plot_library import comparison_plot

def parse_arguments():
    """
    This function takes care of parsing the command-line arguments and
    asking the user for any missing parameters that we need
    """
    parser = argparse.ArgumentParser(description="Creates comparison plots of "
                                     " a number of timeseries files.")
    parser.add_argument("-o", "--output", dest="outfile", required=True,
                        help="output png file")
    parser.add_argument("--epicenter-lat", dest="epicenter_lat", type=float,
                        help="earthquake epicenter latitude")
    parser.add_argument("--epicenter-lon", dest="epicenter_lon", type=float,
                        help="earthquake epicenter longitude")
    parser.add_argument("--st-lat", "--station-latitude", dest="st_lat",
                        type=float, help="station latitude")
    parser.add_argument("--st-lon", "--station-longitude", dest="st_lon",
                        type=float, help="station longitude")
    parser.add_argument("-s", "--station-name", "--station", dest="station",
                        help="station name")
    parser.add_argument("--station-list", dest="station_list",
                        help="station list with latitude and longitude")
    parser.add_argument("--xmin", dest="xmin", type=float,
                        help="xmin for plotting timeseries")
    parser.add_argument("--xmax", dest="xmax", type=float,
                        help="xmax for plotting timeseries")
    parser.add_argument("--xfmin", dest="xfmin", type=float,
                        help="F-min for plotting FAS")
    parser.add_argument("--xfmax", dest="xfmax", type=float,
                        help="F-max for plotting FAS")
    parser.add_argument("--tmin", dest="tmin", type=float,
                        help="T-min for plotting response spectra")
    parser.add_argument("--tmax", dest="tmax", type=float,
                        help="T-max for plotting response spectra")
    parser.add_argument("--lowf", dest="lowf", type=float,
                        help="lowest frequency for filtering")
    parser.add_argument("--highf", dest="highf", type=float,
                        help="highest frequency for filtering")
    parser.add_argument("-c", "--cut", dest="cut",
                        default=False, action='store_true',
                        help="Cut seismogram for plotting")
    parser.add_argument("--acc", dest="acc_plots",
                        default=False, action='store_true',
                        help="Generate acceleration plots instead of velocity")

    parser.add_argument('input_files', nargs='*')
    args = parser.parse_args()

    if args.st_lat is not None and args.st_lon is not None:
        args.st_loc = [args.st_lat, args.st_lon]
    else:
        args.st_loc = None
    if args.epicenter_lat is not None and args.epicenter_lon is not None:
        args.epicenter = [args.epicenter_lat, args.epicenter_lon]
    else:
        args.epicenter = None
    if args.xmin is None:
        args.xmin = 0.0
    if args.xmax is None:
        args.xmax = 30.0
    if args.xfmin is None:
        args.xfmin = 0.1
    if args.xfmax is None:
        args.xfmax = 5.0
    if args.tmin is None:
        args.tmin = 0.1
    if args.tmax is None:
        args.tmax = 10
    if args.xmin >= args.xmax:
        print("[ERROR]: xmin must be smaller than xmax!")
        sys.exit(-1)
    if args.xfmin >= args.xfmax:
        print("[ERROR]: xfmin must be smaller than xfmax!")
        sys.exit(-1)
    if args.tmin >= args.tmax:
        print("[ERROR]: tmin must be smaller than tmax!")
        sys.exit(-1)
    if args.lowf is not None and args.highf is not None:
        if args.lowf >= args.highf:
            print("[ERROR]: lowf must be smaller than highf!")
            sys.exit(-1)

    return args

def process_for_plotting(stations, args):
    """
    Process stations before plotting as indicated by the user

    Basically applies a low/high/band pass butterworth filter
    to all timeseries.
    """
    # Filtering data
    lowf = args.lowf
    highf = args.highf

    if lowf is None and highf is None:
        # Only if needed!
        return stations
    if lowf is not None and highf is not None:
        btype = 'bandpass'
    elif lowf is None and highf is not None:
        btype = "lowpass"
        lowf = 0.0
    else:
        btype = "highpass"
        highf = 0.0

    print("[PROCESSING]: Filter: butter %s %1.1f %1.1f" % (btype,
                                                           lowf, highf))
    for station in stations:
        for i in range(0, 3):
            station[i] = filter_timeseries(station[i],
                                           family='butter', btype=btype,
                                           fmin=lowf, fmax=highf, N=4)

    return stations

def compare_timeseries_main():
    """
    Main function for compare_timeseries
    """
    # Parse command-line options
    args = parse_arguments()
    # Copy inputs
    output_file = args.outfile
    filenames = args.input_files

    # Figure out filtering frequencies, if any
    if args.lowf is None and args.highf is None:
        freqs = "All"
    else:
        if args.lowf is None:
            freqs = "0.0-%1.1fHz" % (args.highf)
        elif args.highf is None:
            freqs = "%1.1fHz-" % (args.lowf)
        else:
            freqs = "%1.1f-%1.1fHz" % (args.lowf, args.highf)

    # Set plot title
    plot_title = None
    if args.station is not None:
        plot_title = "%s, Freq: %s" % (args.station, freqs)

    # Set title if station name provided and epicenter are provided
    if args.station is not None and args.epicenter is not None:
        # Calculate distance if locations are provided
        if args.st_loc is None and args.station_list is not None:
            # Find station coordinates from station list
            st_file = open(args.station_list, 'r')
            for line in st_file:
                line = line.strip()
                if not line:
                    # skip blank lines
                    continue
                if line.startswith("#") or line.startswith("%"):
                    # Skip comments
                    continue
                pieces = line.split()
                if len(pieces) < 3:
                    # Skip line with insufficient tokens
                    continue
                if pieces[2].lower() != args.station.lower():
                    # Not a match
                    continue
                # Match!
                args.st_loc = [float(pieces[1]), float(pieces[0])]
                break
            # All done processing station file
            st_file.close()

        if args.st_loc is not None:
            # Calculate distance here
            distance = calculate_distance(args.epicenter, args.st_loc)
            # Set plot title
            plot_title = "%s, Dist: ~%dkm, Freq: %s" % (args.station,
                                                        distance, freqs)

    # Read data
    stations = [read_file(filename) for filename in filenames]
    filenames = [os.path.basename(filename) for filename in filenames]

    # Perform any processing requested by the user
    stations = process_for_plotting(stations, args)

    # Create plot
    comparison_plot(args, filenames, stations,
                    output_file, plot_title=plot_title)

# ============================ MAIN ==============================
if __name__ == "__main__":
    compare_timeseries_main()
# end of main program
