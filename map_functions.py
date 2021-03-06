import numpy as np
import time
from scipy.interpolate import interp1d
from scipy.interpolate import RectBivariateSpline
from numba import jit
from matplotlib import pyplot as plt
import pandas as pd

# Compton-y --> temperature #{{{
def g(x):# Spectral Function
    return x*(np.tanh(0.5*x))**(-1.) - 4.
def T(cosmology, y):
    return cosmology['TCMB'] * cosmology['gnu'] * y * 1e6 # in uK
#}}}

#################################
###### Map making functions #####
#################################
@jit
def throw_clusters(cluster_number, final_map, this_map, central_pixels_x, central_pixels_y):#{{{
    central_pixel_x_this_map = (this_map.shape[0]-1)/2
    central_pixel_y_this_map = (this_map.shape[1]-1)/2
    for kk in xrange(cluster_number):                                                                     
        extent_x_right = final_map.shape[0] - int(central_pixels_x[kk]) - 1
        extent_x_left  = int(central_pixels_x[kk])
        extent_y_up    = final_map.shape[1] - int(central_pixels_y[kk]) - 1
        extent_y_down  = int(central_pixels_y[kk])
        # number of pixels free in all directions from the central pixel
        # actually, the this_map can be smaller:
        extent_x_right = (np.array([extent_x_right, central_pixel_x_this_map])).min()
        extent_x_left  = (np.array([extent_x_left, central_pixel_x_this_map])).min()
        extent_y_up    = (np.array([extent_y_up, central_pixel_y_this_map])).min()
        extent_y_down  = (np.array([extent_y_down, central_pixel_y_this_map])).min()
        final_map[
                int(central_pixels_x[kk])-extent_x_left:int(central_pixels_x[kk])+extent_x_right+1,
                int(central_pixels_y[kk])-extent_y_down:int(central_pixels_y[kk])+extent_y_up+1
                ] += this_map[
                        central_pixel_x_this_map-extent_x_left:central_pixel_x_this_map+extent_x_right+1,
                        central_pixel_y_this_map-extent_y_down:central_pixel_y_this_map+extent_y_up+1
                        ]
    return final_map
#}}}

# ( only these functions should be called from outside )
def map_generate_linear_density_field(z_index, numerics, cosmology, path) :#{{{
    f = np.load(path + '/linear_density_Cells.npz')
    ell = f['ell']
    Cell = f['Cell'][:,z_index]
    delta_map = np.ones((int(numerics['map_size']/numerics['map_pixel_size']),int(numerics['map_size']/numerics['map_pixel_size'])))
    fine_X = np.linspace(0., 1., num = delta_map.shape[0])
    fine_Y = np.linspace(0., 1., num = delta_map.shape[1])

    exponent = int(np.floor(np.log2(delta_map.shape[0])))-1
    coarse_delta_map = np.zeros((2**exponent, 2**exponent))
    coarse_X = np.linspace(0., 1., num = coarse_delta_map.shape[0])
    coarse_Y = np.linspace(0., 1., num = coarse_delta_map.shape[1])
    coarse_pixel_size = numerics['map_size']/float(coarse_delta_map.shape[0])


    #### TODO : this is only a test that things propagate correctly
    #### REMOVE LATER!
    #interesting_indices = np.where((ell<210)&(ell>190))
    #Cell[interesting_indices] = 1e6*np.max(Cell)

    # cut powerspectrum at non-linear scale (bias only applies on linear scales)
    z = 0.5*(numerics['map_z_boundaries'][z_index] + numerics['map_z_boundaries'][z_index+1])
    theta_nonlinear = numerics['map_nonlinear_scale']/(cosmology['cosmo_object'].angular_diameter_distance(z).value*cosmology['h'])
    #print 'nonlinear theta (deg):'
    #print theta_nonlinear*180./np.pi
    l_nonlinear = np.pi/theta_nonlinear
    Cell[np.where(ell>l_nonlinear)] = 0.

    Cell_interpolator = interp1d(ell, Cell, bounds_error = False, fill_value = 0.)
    onesvec = np.ones(coarse_delta_map.shape[0])
    inds = (np.arange(coarse_delta_map.shape[0])+0.5-coarse_delta_map.shape[0]/2.)/(coarse_delta_map.shape[0]-1.)
    X = np.outer(onesvec, inds)
    Y = np.transpose(X)
    R = np.sqrt(X**2. + Y**2.)
    ell_scale_factor = 2.*np.pi/coarse_pixel_size
    ell2d = R * ell_scale_factor
    Cell2d = Cell_interpolator(ell2d)
    random_array_for_delta = np.random.normal(0,1,coarse_delta_map.shape)
    FT_random_array_for_delta = np.fft.fft2(random_array_for_delta)
    FT_2d = np.sqrt(Cell2d) * FT_random_array_for_delta
    coarse_delta_map = np.fft.ifft2(np.fft.fftshift(FT_2d))
    coarse_delta_map /= coarse_pixel_size
    coarse_delta_map = np.real(coarse_delta_map)

    delta_map_interpolator = RectBivariateSpline(coarse_X, coarse_Y, coarse_delta_map)
    delta_map = delta_map_interpolator(fine_X, fine_Y)

    #plt.matshow(delta_map)
    #plt.show()

    #meas_ell, meas_Cell = map_get_powerspectrum(numerics, delta_map)
    #plt.loglog(ell, Cell, label = 'input')
    #plt.loglog(meas_ell, 5.3*meas_Cell, label = 'output')
    #plt.xlim(min(ell), max(ell))
    #plt.legend()
    #plt.show()

    return delta_map
#}}}
def map_generate_final_map(numerics, cosmology, path, index):#{{{
    start_total = time.time()
    f = np.load(path + '/dndOmega.npz')
    dndOmega = f['dndOmega']
    f = np.load(path + '/yprofiles.npz')
    thetas = f['thetas']
    yprofiles = f['yprofiles']
    if numerics['map_include_bias'] :
        f = np.load(path + '/bias.npz')
        bias = f['bias']
    # consistency checks#{{{
    if dndOmega.shape[0] != numerics['map_Npoints_M']:
        print 'dndOmega mass problem'
        print 'dndOmega has ' + str(dndOmega.shape[0]) + ' mass entries'
        print 'while we have ' + str(numerics['map_Npints_M']) + ' mass grid points'
        return
    if dndOmega.shape[1] != numerics['map_Npoints_z']:
        print 'dndOmega redshift problem'
        print 'dndOmega has ' + str(dndOmega.shape[1]) + ' redshift entries'
        print 'while we have ' + str(numerics['map_Npints_z']) + ' redshift grid points'
        return
    if len(yprofiles) != numerics['map_Npoints_M']:
        print 'yprofiles mass problem'
        print 'yprofiles has ' + str(len(yprofiles)) + ' mass entries'
        print 'while we have ' + str(numerics['map_Npoints_M']) + ' mass grid points'
        return
    if len(yprofiles[0]) != numerics['map_Npoints_z']:
        print 'yprofiles redshift problem'
        print 'yprofiles has ' + str(len(yprofiles[0])) + ' redshift entries'
        print 'while we have ' + str(numerics['map_Npoints_z']) + ' redshift grid points'
        return
    #}}}
    # prepare the final map
    final_map = np.zeros((int(numerics['map_size']/numerics['map_pixel_size']),int(numerics['map_size']/numerics['map_pixel_size'])))
    map_area = final_map.shape[0]*numerics['map_pixel_size']*final_map.shape[1]*numerics['map_pixel_size']
    for jj in xrange(numerics['map_Npoints_z']):
        if numerics['verbose'] :
            print str(jj)
        start = time.time()
        if numerics['map_include_bias'] :
        # fo each redshift bin, compute one random realization of the overdensity field
            delta_map = map_generate_linear_density_field(jj, numerics, cosmology, path)
            delta_map = delta_map.flatten()
        for ii in xrange(numerics['map_Npoints_M']):
            if numerics['map_Poisson']:
                cluster_number = np.random.poisson(dndOmega[ii,jj]*map_area)
            else :
                middle = dndOmega[ii,jj]*map_area
                lower = np.floor(middle)
                upper = np.ceil(middle)
                if np.random.rand() < (middle - lower):
                    cluster_number = int(upper)
                else:
                    cluster_number = int(lower)
            if cluster_number > 0:
                if numerics['map_include_bias'] :
                    #probabilities = 1. + bias[ii,jj] * delta_map
                    #probabilities[np.where(probabilities<0.)] = 0.
                    #probabilities /= sum(probabilities)
                    probabilities = map_get_probabilities(bias[ii,jj], delta_map)
                    central_pixels = np.random.choice(len(delta_map), p = probabilities, replace = True, size = cluster_number)
                    central_pixels_x = np.zeros(cluster_number, dtype = int)
                    central_pixels_y = np.zeros(cluster_number, dtype = int)
                    for kk in xrange(cluster_number) :
                        central_pixels_x[kk] = central_pixels[kk]/final_map.shape[0]
                        central_pixels_y[kk] = central_pixels[kk]%final_map.shape[0]
                else :
                    central_pixels_x = np.random.random_integers(0, final_map.shape[0]-1, size = cluster_number)
                    central_pixels_y = np.random.random_integers(0, final_map.shape[1]-1, size = cluster_number)
                random_offset_x = np.random.rand()-0.5
                random_offset_y = np.random.rand()-0.5
                t = thetas[ii][jj]
                y = yprofiles[ii][jj]
                y_interpolator = interp1d(t, y, kind = 'cubic', bounds_error = False, fill_value = (max(y), 0.))
                T_of_theta = lambda theta: T(cosmology, y_interpolator(theta))
                this_map = np.zeros((2*int(max(t)/numerics['map_pixel_size'])+5, 2*int(max(t)/numerics['map_pixel_size'])+5)) # want central pixel to be on center of the cluster
                pixel_indices_x = np.linspace(-(this_map.shape[0]-1)/2.,(this_map.shape[0]-1)/2.,num = this_map.shape[0])
                pixel_indices_y = np.linspace(-(this_map.shape[1]-1)/2.,(this_map.shape[1]-1)/2.,num = this_map.shape[1])
                # average over angles
                nn = 0
                for kk in xrange(-numerics['map_grid_per_pixel'],numerics['map_grid_per_pixel']+1):
                    for ll in xrange(-numerics['map_grid_per_pixel'],numerics['map_grid_per_pixel']+1):
                        angles = numerics['map_pixel_size'] * np.sqrt(np.add.outer((pixel_indices_x + random_offset_x + float(kk)/float(numerics['map_grid_per_pixel']+0.5))**2.,(pixel_indices_y + random_offset_y + float(ll)/float(numerics['map_grid_per_pixel']+0.5))**2.))
                        this_map += T_of_theta(angles)
                        nn += 1
                this_map *= 1./float(nn)
                final_map = throw_clusters(cluster_number, final_map, this_map, central_pixels_x, central_pixels_y)
        end = time.time()
        if numerics['verbose'] :
            print str((numerics['map_Npoints_z']-jj)*(end-start)/60.) + ' minutes remaining in map_generate_final_map'
            print 'I am in index = ' + str(index)
    # need to take a subset of the final map, since otherwise we're getting a bias (centres of clusters are currently always in the map)
    spare_pixels_horizontal = int((1.-numerics['map_fraction'])/2.*final_map.shape[0])
    spare_pixels_vertical   = int((1.-numerics['map_fraction'])/2.*final_map.shape[1])
    hist = map_get_histogram(final_map[spare_pixels_horizontal:-spare_pixels_horizontal-1,spare_pixels_vertical:-spare_pixels_vertical-1])
    np.savez(path + '/p_' + str(index) + '.npz', p = hist)
    #inal_map = final_map[spare_pixels_horizontal:-spare_pixels_horizontal-1,spare_pixels_vertical:-spare_pixels_vertical-1]

    # Now do the apodization to get the power spectrum
    final_map[:spare_pixels_horizontal, :] *= np.linspace(0.*np.ones(final_map.shape[1]), 1.*np.ones(final_map.shape[1]), num = spare_pixels_horizontal, axis = 0)
    final_map[-spare_pixels_horizontal:, :] *= np.linspace(0.*np.ones(final_map.shape[1]), 1.*np.ones(final_map.shape[1]), num = spare_pixels_horizontal, axis = 0)[::-1, :]
    final_map[:, :spare_pixels_vertical] *= np.linspace(0.*np.ones(final_map.shape[0]), 1.*np.ones(final_map.shape[0]), num = spare_pixels_vertical, axis = 1)
    final_map[:, -spare_pixels_vertical:] *= np.linspace(0.*np.ones(final_map.shape[0]), 1.*np.ones(final_map.shape[0]), num = spare_pixels_vertical, axis = 1)[:, ::-1]
    #plt.matshow(final_map)
    #plt.show()
    #np.savez(path + '/final_map_' + str(index) + '.npz', final_map = final_map)
    ell, Cell = map_get_powerspectrum(numerics, final_map)
    np.savez(path + '/PS_' + str(index) + '.npz', ell = ell, Cell = Cell)
    end_total = time.time()
    if numerics['verbose'] :
        print 'used ' + str((end_total - start_total)/60.) + ' minutes in total'
    #plt.loglog(ell, Cell)
    #plt.savefig('tSZ_power_spectrum.pdf')
    #plt.show()
#}}}

@jit(nopython=True)
def map_get_probabilities(bias, delta_map) :#{{{
    probabilities = 1. + bias*delta_map
    probabilities[np.where(probabilities<0.)] = 0.
    probabilities /= np.sum(probabilities)
    return probabilities
#}}}
def map_generate_random_noise(numerics, cosmology, path, index) :#{{{
    noise_map = np.zeros((int(numerics['map_size']/numerics['map_pixel_size']),int(numerics['map_size']/numerics['map_pixel_size'])))
    onesvec = np.ones(noise_map.shape[0])
    inds = (np.arange(noise_map.shape[0])+0.5-noise_map.shape[0]/2.)/(noise_map.shape[0]-1.)
    X = np.outer(onesvec, inds)
    Y = np.transpose(X)
    R = np.sqrt(X**2. + Y**2.)
    ell_scale_factor = 2.*np.pi/numerics['map_pixel_size']
    ell2d = R * ell_scale_factor
    Cell2d = cosmology['noise_power'](ell2d)
    random_array_for_T = np.random.normal(0,1,noise_map.shape)
    FT_random_array_for_T = np.fft.fft2(random_array_for_T)
    FT_2d = np.sqrt(Cell2d) * FT_random_array_for_T
    y_map = np.fft.ifft2(np.fft.fftshift(FT_2d))
    y_map /= numerics['map_pixel_size']
    noise_map = np.real(y_map)
    noise_map = T(cosmology, noise_map)
    np.savez(path + '/noise_' + str(index) + '.npz', noise = noise_map)
#}}}

def map_get_histogram(tSZ_map) :
    bin_boundaries = -np.arange(0., 100.)[::-1]
    hist, edges = np.histogram(tSZ_map.flatten(), bin_boundaries)
    hist = hist/float(sum(hist))
    return hist

#@jit(nopython = True)
def get_Cell(cut, PSmap) :
    #ell2d = ell2d.flatten()
    #PSmap = PSmap.flatten()
    avg = pd.DataFrame(PSmap).groupby(cut).agg('mean').values
    return avg

def map_get_powerspectrum(numerics, tSZ_map) :
    exponent = int(np.ceil(np.log2(tSZ_map.shape[0])))
    left_number = int(np.ceil((2**exponent - tSZ_map.shape[0])/2.))
    right_number = int(np.floor((2**exponent - tSZ_map.shape[0])/2.))
    tSZ_map = np.pad(tSZ_map, ((left_number, right_number), (left_number, right_number)), 'constant', constant_values = 0.)
    print tSZ_map.shape
    #plt.matshow(tSZ_map)
    #plt.show()
    Fmap = np.fft.ifft2(np.fft.fftshift(tSZ_map))
    PSmap = np.fft.fftshift(np.real(np.conj(Fmap)*Fmap))
    Cell = get_Cell(numerics['PS_pd_cut'], PSmap.flatten())
    ell_centres = numerics['PS_ell_centres']
    return (ell_centres, Cell*np.sqrt(numerics['map_pixel_size'])*2)
