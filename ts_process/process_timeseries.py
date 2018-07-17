#!/usr/bin/env python3
"""
Copyright 2010-2018 University Of Southern California

Licensed under the Apache License, Version 2.0 (the "License");
you may not use this file except in compliance with the License.
You may obtain a copy of the License at

 http://www.apache.org/licenses/LICENSE-2.0

Unless required by applicable law or agreed to in writing, software
distributed under the License is distributed on an "AS IS" BASIS,
WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
See the License for the specific language governing permissions and
limitations under the License.

The program is to read input seismograms; process their signals.
"""
from __future__ import division, print_function
import os
import sys
import argparse

from file_utilities import write_bbp, read_stamp, read_files
from ts_library import rotate_timeseries, process_station_dt, \
    check_station_data, filter_timeseries, seism_cutting, seism_cutting

def filter_data(timeseries, frequencies):
    """
    Filter timeseries using the frequencies specified by the user
    """
    if len(frequencies) == 1:
        fmin = 0.0
        fmax = frequencies[0]
        btype = 'lowpass'
    elif len(frequencies) == 2:
        fmin = frequencies[0]
        fmax = frequencies[1]
        btype = 'bandpass'
    else:
        print("[ERROR]: Must specify one or two frequencies for filtering!")
        sys.exit(-1)

    filter_timeseries(timeseries, family='butter', btype=btype,
                      fmin=fmin, fmax=fmax,
                      N=4, rp=0.2, rs=100)

    return timeseries
#end filter_data

def synchronize_all_stations(obs_data, stations, stamp, eqtimestamp, leading):
    """
    synchronize the stating time and ending time of data arrays
    obs_data = recorded data (optional); stations = simulation signal(s)
    """
    # If we have a recorded data time stamp
    if stamp is not None and obs_data is not None:
        start = stamp[0]*3600 + stamp[1]*60 + stamp[2]
        eq_time = eqtimestamp[0]*3600 + eqtimestamp[1]*60 + eqtimestamp[2]
        sim_start = eq_time - leading

        for i in range(0, 3):
            # synchronize the start time
            if start < sim_start:
                # data time < sim time < earthquake time; cutting data array
                obs_data[i] = seism_cutting('front', (sim_start - start),
                                            20, obs_data[i])
            elif start > eq_time:
                # sim time < earthquake time < data time; adding zeros in front
                obs_data[i] = seism_appendzeros('front', (start - eq_time),
                                                20, obs_data[i])
                for station in stations:
                    station[i] = seism_cutting('front', (eq_time - sim_start),
                                               20, station[i])
            else:
                # sim time < data time < earthquake time; adding zeros
                obs_data[i] = seism_appendzeros('front', (start - sim_start),
                                                20, obs_data[i])

    # synchronize the ending time
    if obs_data is not None:
        obs_dt = obs_data[0].dt
        obs_samples = obs_data[0].samples
        obs_time = obs_dt * obs_samples
    else:
        obs_time = None

    # Find target timeseries duration
    target_time = None
    if obs_time is not None:
        target_time = obs_time
    for station in stations:
        station_dt = station[0].dt
        station_samples = station[0].samples
        station_time = station_dt * station_samples
        if target_time is None:
            target_time = station_time
            continue
        target_time = min(target_time, station_time)

    # Work on obs_data
    if obs_data is not None:
        for i in range(0, 3):
            if obs_time > target_time:
                obs_data[i] = seism_cutting('end', (obs_time - target_time),
                                            20, obs_data[i])
        obs_samples = obs_data[0].samples
        obs_time = obs_dt * obs_samples

    # Work on simulated data
    for station in stations:
        for i in range(0, 3):
            sim_dt = station[i].dt
            sim_samples = station[i].samples
            sim_time = sim_dt * sim_samples
            if sim_time > target_time:
                station[i] = seism_cutting('end', (sim_time - target_time),
                                           20, station[i])

    # scale the data if they have one sample in difference after synchronizing
    total_samples = None
    if obs_data is not None:
        total_samples = obs_samples
    for station in stations:
        sim_samples = station[0].samples
        if total_samples is None:
            total_samples = sim_samples
            continue
        total_samples = max(sim_samples, total_samples)

    # For obs_data
    if obs_data is not None:
        for i in range(0, 3):
            if obs_data[i].samples == total_samples - 1:
                obs_data[i] = seism_appendzeros('end', obs_data[i].dt,
                                                20, obs_data[i])
    # For simulated data
    for station in stations:
        for i in range(0, 3):
            if station[i].samples == total_samples - 1:
                station[i] = seism_appendzeros('end', station[i].dt,
                                               20, station[i])

    return obs_data, stations
# end of synchronize_all_stations

def process(obs_file, obs_data, stations, params):
    """
    This method processes the signals in each pair of stations.
    Processing consists on scaling, rotation, decimation, alignment
    and other things to make both signals compatible to apply GOF method.
    obs_data: recorded data
    stations: simulation
    """
    # rotate synthetics
    stations = [rotate_timeseries(station,
                                  params['azimuth']) for station in stations]

    # process signals to have the same dt
    if obs_data is not None:
        obs_data = process_station_dt(obs_data,
                                      params['targetdt'],
                                      params['decifmax'])
    stations = [process_station_dt(station,
                                   params['targetdt'],
                                   params['decifmax']) for station in stations]

    # Read obs_file timestamp if needed
    stamp = None
    if obs_data is not None:
        stamp = read_stamp(obs_file)

    # synchronize starting and ending time of data arrays
    obs_data, stations = synchronize_all_stations(obs_data,
                                                  stations,
                                                  stamp,
                                                  params['eq_time'],
                                                  params['leading'])

    # Check number of samples
    if obs_data is not None:
        num_samples = obs_data[0].samples
    else:
        num_samples = stations[0][0].samples

    for station in stations:
        if station[0].samples != num_samples:
            print("[ERROR]: two timseries do not have the same number"
                  " of samples after processing.")
            sys.exit(-1)

    # Check the data
    if obs_data is not None:
        if not check_station_data(obs_data):
            print("[ERROR]: processed recorded data contains errors!")
            sys.exit(-1)
    for station in stations:
        if not check_station_data(station):
            print("[ERROR]: processed simulated data contains errors!")
            sys.exit(-1)

    # final filtering step
    if obs_data is not None:
        for i in range(0, 3):
            obs_data[i] = filter_data(obs_data[i], params['frequencies'])
    for station in stations:
        for i in range(0, 3):
            station[i] = filter_data(station[i], params['frequencies'])

    # All done
    return obs_data, stations
# end of process

def parse_arguments():
    """
    This function takes care of parsing the command-line arguments and
    asking the user for any missing parameters that we need
    """
    parser = argparse.ArgumentParser(description="Processes a number of "
                                     "timeseries files and prepares them "
                                     "for plotting.")
    parser.add_argument("--obs", dest="obs_file",
                        help="input file containing recorded data")
    parser.add_argument("--leading", type=float, dest="leading",
                        help="leading time for the simulation (seconds)")
    parser.add_argument("--eq-time", dest="eq_time",
                        help="earthquake start time (HH:MM:SS.CCC)")
    parser.add_argument("--azimuth", type=float, dest="azimuth",
                        help="azimuth for rotation (degrees)")
    parser.add_argument("--dt", type=float, dest="targetdt",
                        help="target dt for all processed signals")
    parser.add_argument("--decimation-freq", type=float, dest="decifmax",
                        help="maximum frequency for decimation")
    parser.add_argument("--freqs", dest="frequencies",
                        help="frequencies to filter")
    parser.add_argument("--output-dir", dest="outdir",
                        help="output directory for the outputs")
    parser.add_argument('input_files', nargs='*')
    args = parser.parse_args()

    # Input files
    files = args.input_files
    obs_file = args.obs_file

    if len(files) < 1 or len(files) == 1 and obs_file is None:
        print("[ERROR]: Please provide at least two timeseries to process!")
        sys.exit(-1)

    # Check for missing input parameters
    params = {}

    if args.outdir is None:
        print("[ERROR]: Please provide output directory!")
    else:
        params['outdir'] = args.outdir

    if args.frequencies is None:
        print("[ERROR]: Please provide sequence of frequencies for filtering!")
    else:
        freqs = args.frequencies.replace(',', ' ').split()
        if len(freqs) < 1:
            print("[ERROR]: Invalid frequencies!")
            sys.exit(-1)
        try:
            freqs = [float(freq) for freq in freqs]
        except ValueError:
            print("[ERROR]: Invalid frequencies!")
        for i in range(0, len(freqs)-1):
            if freqs[i] >= freqs[i+1]:
                print("[ERROR]: Invalid sequence of sample rates!")
        params['frequencies'] = freqs

    if args.decifmax is None:
        print("[ERROR]: Please enter maximum frequency for decimation!")
    else:
        params['decifmax'] = args.decifmax

    if args.targetdt is None:
        print("[ERROR]: Please provide a target DT to be used in all signals!")
    else:
        params['targetdt'] = args.targetdt

    # Copy azimuth parameter for rotation, None means no rotation
    params['azimuth'] = args.azimuth

    if args.eq_time is None:
        print("[ERROR]: Please provide earthquake time!")
    else:
        tokens = args.eq_time.split(':')
        if len(tokens) < 3:
            print("[ERROR]: Invalid time format!")
            sys.exit(-1)
        try:
            params['eq_time'] = [float(token) for token in tokens]
        except ValueError:
            print("[ERROR]: Invalid time format!")
            sys.exit(-1)

    if args.leading is None:
        print("[ERROR]: Please enter the simulation leading time!")
    else:
        params['leading'] = args.leading

    return obs_file, files, params

def process_main():
    """
    Main function for processing seismograms
    """
    # First let's get all aruments that we need
    obs_file, input_files, params = parse_arguments()

    # Read input files
    obs_data, stations = read_files(obs_file, input_files)

    # Process signals
    obs_data, stations = process(obs_file, obs_data, stations, params)

    # Write processed files
    if obs_data is not None:
        obs_file_out = os.path.join(params['outdir'],
                                    "p-%s" % obs_file.split('/')[-1])
        write_bbp(obs_file, obs_file_out, obs_data)

    for input_file, station in zip(input_files, stations):
        out_file = os.path.join(params['outdir'],
                                "p-%s" % input_file.split('/')[-1])
        write_bbp(input_file, out_file, station)
# end of process_main

# ============================ MAIN ==============================
if __name__ == "__main__":
    process_main()
# end of main program
