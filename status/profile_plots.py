#!/usr/bin/env python
# -*- coding: utf-8 -*-

import matplotlib
matplotlib.use('AGG')

from netCDF4 import Dataset
from netcdftime import utime
from functools import wraps
import matplotlib.pyplot as plt
import matplotlib.dates as mdates
import numpy as np
import numpy.ma as ma
import os
import requests
import sys
import cmocean
import matplotlib.cm as cm
import time


PARAMETERS = {
    'temperature': {
        'cmap': cmocean.cm.thermal,
        'display': u'Temperature (°C)'
    },
    'salinity': {
        'cmap': cmocean.cm.haline,
        'display': u'Salinity (1e-3)'
    },
    'conductivity': {
        'cmap': cmocean.cm.haline,
        'display': u'Conductivity (S m-1)'
    },
    'density': {
        'cmap': cmocean.cm.dense,
        'display': u'Density (kg m-3)',
    }
}


def get_times(nc, x, z):
    '''
    Converts an array of timestamps to the matplotlib epoch and builds a
    meshgrid of the timestamps for each profile

    :param netCDF4.Dataset nc: An open netCDF file
    :param numpy.ndarray x: An array of time values
    :param numpy.ndarray z: A multi-dimensional array representing the profiles
    '''
    xv = np.ones(z.shape, dtype=np.object)
    converter = utime(nc.variables['time'].units)
    for i, timestamp in enumerate(np.squeeze(x)):
        xv[i, :] = converter.num2date(timestamp)

    xv = mdates.date2num(xv)
    return xv


def generate_profile_plot(x, y, z, cmap, title='Glider Profiles', ylabel='Pressure (dbar)', zlabel='Temperature'):
    '''
    Renders a matplotlib profile plot

    :param numpy.ndarray x: A grid of timestamps (masked arrays welcome)
    :param numpy.ndarray y: A grid of depths     (masked arrays welcome)
    :param numpy.ndarray z: A grid of values     (masked arrays welcome)
    :param cmap: The colormap to use on the plot
    :param str title: Title of the plot
    :param str ylabel: The label to display along the Y-Axis
    :param str zlabel: The label to display along the color bar legend
    '''
    fig, ax = plt.subplots()
    std = np.nanstd(z)
    mean = np.nanmean(z)
    vmin = mean - 2 * std
    vmax = mean + 2 * std
    if vmin < 0:
        vmin = 0
    im = ax.scatter(x, y, c=z, cmap=cmap, vmin=vmin, vmax=vmax)
    ax.set_title(title)
    ax.invert_yaxis()
    date_format = mdates.DateFormatter('%Y-%m-%d')
    ax.xaxis.set_major_formatter(date_format)
    ax.set_ylabel(ylabel)
    colorbar = fig.colorbar(im, ax=ax)
    colorbar.set_label(zlabel)
    fig.autofmt_xdate()

    return fig


def plot_from_nc(title, nc, parameter, filepath):
    '''
    Plot the parameter from a netCDF file. This function will take into
    consideration deployments that have a zig-zag pattern of profiles and
    deployments that contain non-fill NaN values.

    :param str title: Title of the plot
    :param netCDF4.Dataset nc: An open netCDF file
    :param str parameter: Parameter to plot
    :param str filepath: Location to save the figure to (PNG)
    '''
    x, y, z = get_variables(nc, parameter)

    # Remove empty timesteps
    if hasattr(x, 'mask'):
        y = y[~x.mask]
        z = z[~x.mask]
        x = x[~x.mask]

    total_mask = y.mask | z.mask | np.isnan(y) | np.isnan(z)
    y.mask = total_mask
    z.mask = total_mask

    z = np.squeeze(z)
    y = np.squeeze(y)
    x = get_times(nc, x, z)

    title = title + ' ' + parameter[0].upper() + parameter[1:] + ' Profiles'
    fig = generate_profile_plot(x, y, z, PARAMETERS[parameter]['cmap'], title=title, zlabel=PARAMETERS[parameter]['display'])
    fig.set_size_inches(20, 5)
    fig.savefig(filepath, dpi=100)
    plt.close(fig)


def get_variables(nc, parameter):
    y = nc.variables['pressure'][0, :, :]
    z = nc.variables[parameter][0, :, :]
    x = nc.variables['time'][0, :]
    return x, y, z


def iter_deployments():
    '''
    Iterates over all of the GliderDAC deployments and returns the dictionary
    containing the deployment attributes.
    '''
    url = 'https://gliders.ioos.us/providers/api/deployment'
    response = requests.get(url, timeout=20)
    response.raise_for_status()
    results = response.json()
    for deployment in results['results']:
        yield deployment


def plot_deployment(deployment, path):
    '''
    Plot the parameters for a deployment

    :param dict deployment: A deployment object
    :param str path: Folder path to where to store the images
    '''
    thredds_url = deployment['dap']
    with Dataset(thredds_url, 'r') as nc:
        for parameter in PARAMETERS:
            filename = os.path.join(path, '%s.png' % parameter)
            try:
                plot_from_nc(deployment['name'], nc, parameter, filename)
            except Exception:
                print("Failed to generate plot for %s" % parameter)
                continue
            print(filename)


def fix_profiles(y, z):
    '''
    Inverts the profile in-place if it is an upcast, so the mesh has a correct y-axis
    '''
    for i in range(y.shape[0]):
        # if profile is flipped
        if len(y[i][~y[i].mask]) and y[i][~y[i].mask][0] > y[i][~y[i].mask][-1]:
            y[i][~y[i].mask] = y[i][~y[i].mask][::-1]
            z[i][~z[i].mask] = z[i][~z[i].mask][::-1]


def main(args):
    '''
    Builds a directory of profile plots from the GliderDAC deployments
    '''
    for deployment in iter_deployments():
        try:
            for deployment_filter in args.deployment or []:
                if deployment_filter in deployment['deployment_dir']:
                    break
            else:
                if args.deployment:
                    continue
            print(deployment['deployment_dir'])
            path = os.path.join(args.path, deployment['deployment_dir'])
            if not os.path.exists(path):
                os.makedirs(path)
            plot_deployment(deployment, path)
        except Exception:
            print("Error processing")
            from traceback import print_exc
            print_exc()

    return 0


if __name__ == '__main__':
    from argparse import ArgumentParser
    parser = ArgumentParser(description=main.__doc__)
    parser.add_argument('path', help='Path to where to write the profiles')
    parser.add_argument('-d', '--deployment', action='append', help='Which deployment to build')
    args = parser.parse_args()

    sys.exit(main(args))
