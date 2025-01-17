'''

Config file not specified!

    $ python dictionary_learn_from_config.py config.yaml

Make sure "dictionary_learn_fx.py" is in the same directory as this code.
Output files to OUTPUT/ is default.

'''
import numpy as np
# import pandas as pd
import sys
import time
# from numba import jit, njit     # use numba to accelerate key functions in the algorithm (by roughly a factor of 3!)
# from glob import glob
from numpy.random import default_rng
import matplotlib.pyplot as plt
from pathlib import Path
import dictionary_learn_fx as fx # type: ignore
import yaml


if len(sys.argv) == 1:
    print(__doc__)
    exit()

config_file = sys.argv[1]

with open(config_file, 'r') as file:
    config = yaml.safe_load(file)

# load simulated spectra data
filename = config['Filenames_locations']['filename']
eazy_templates_location = config['Filenames_locations']['eazy_templates_location']
filter_location = config['Filenames_locations']['filter_location']
output_dirname = config['Filenames_locations']['OUTPUT']

Ndat = config['Parameters']['Ndat']
learning_rate0 = config['Parameters']['learning_rate0']
learning_rate_cali = config['Parameters']['learning_rate_cali']
SNR = config['Parameters']['SNR']
error_method = config['Parameters']['error_method']
add_fluctuations = config['Parameters']['add_fluctuations']     # Add random fluctuations to fluxes based on error columns as gaussian
flux_fluctuation_scaling = config['Parameters']['flux_fluctuation_scaling']
probline = config['Parameters']['probline']
Ncalibrators = config['Parameters']['Ncalibrators']

Ndict = config['Dictionary']['Ndict']
num_EAZY_as_dict = config['Dictionary']['num_EAZY_as_dict']
dicts_fluctuation_scaling_const = config['Dictionary']['dict_fluctuation_scaling_start']
if type(dicts_fluctuation_scaling_const) == str:
    dicts_fluctuation_scaling_const = float(dicts_fluctuation_scaling_const)
dict_fluctuation_scaling_base = config['Dictionary']['dict_fluctuation_scaling_base']
template_scale = config['Dictionary']['dict_scale']

rescale_constant = 8    # in additional to rescaling input data to similar noise level as initial dicts, also multiply input catalog by this number to make it a bit bigger
f_lambda_mode = config['Settings']['f_lambda_mode']    # fitting in f_lambda or f_nu
rescale_input = config['Settings']['rescale_input']    # if True, rescale the input catalog to comparable standard deviation level to Brown galaxies
fix_calibration_gals = config['Settings']['fix_calibration_gals']
algorithm = config['Settings']['algorithm']             # choose which algorithm to use for dictionary updates, 0: psudo-inverse vector method, 1: paper method
N_AB_loops = config['Settings']['update_loops']         # if algorithm = 1, number of loops to run updates on dictionaries
convolve_filters = config['Settings']['convolve_filters']
convolve_filter = convolve_filters[0] # choose to convolve templates with filter or not in the first stage of optimized grid search
last_stage_convolve_filter = convolve_filters[1]   # whether to colvolve with filters in the last stage of grid search 
fitting_convolve_filter = convolve_filters[2] # Whether to convolve with filters in the end when fitting final redshifts

c = 3e18

i_calibrator_galaxies_input = np.array([145, 361, 166, 137, 338,   2, 158, 375, 236, 237, 188, 343, 265,
            120, 254,   7,  45,  12, 274,  62, 108, 379, 396, 115, 301, 369,
            43, 198, 210, 294, 329, 180, 380, 194, 101, 347,   5,  17, 285,
            163, 331,  53,  29,  34, 279, 334, 251,  61,  74, 178])
if Ndat < 400:
    i_calibrator_galaxies_input = np.random.randint(low=0, high=Ndat, size=Ncalibrators)


z_fitting_max = config['Zgrid']['z_fitting_max']
# optimized zgrid setting and initialization
zgrid_seps = config['Zgrid']['zgrid_separation']
zgrid_seps.append(z_fitting_max)
zgrid_seps = np.array(zgrid_seps)
zgrid_stepsizes = np.array(config['Zgrid']['zgrid_stepsizes'])  # This needs to be shorter than zgrid_seps by 1 element
zgrid_searchsize = max(max(zgrid_stepsizes), config['Zgrid']['min_zgrid_searchsize'])  # search grid size to the left and right should be at least 0.02 but equal to the largest step size
zgrid_errsearchsize = config['Zgrid']['zgrid_errsearchsize']
zgrid = fx.generate_zgrid(zgrid_seps, zgrid_stepsizes, z_fitting_max)

# Initialize dictionaries as noise with different level of fluctuation
dictionary_fluctuation_scaling = np.array([dicts_fluctuation_scaling_const/(dict_fluctuation_scaling_base**i) for i in range(Ndict-1)])
# dictionary_fluctuation_scaling = np.array([dicts_fluctuation_scaling_const/(dict_fluctuation_scaling_base**(2*i/Ndict)) for i in range(Ndict-1)])


if len(output_dirname) > 0 and output_dirname[-1] != '/':
    output_dirname = output_dirname + '/'
output_dir = Path(output_dirname)
if len(output_dirname) > 0 and not output_dir.is_dir():
    output_dir.mkdir()


if __name__ == "__main__":
    print(f"Algorithm = {algorithm}")
    print(f"Ndat = {Ndat}")
    print(f"Ndict = {Ndict}")
    print(f"Rescale input: {rescale_input}")
    # print(f"Convolving filters: 1st stage:{convolve_filter}, 2nd stage:{last_stage_convolve_filter}, fitting:{fitting_convolve_filter}")
    print(f"Fix calibration gals: {fix_calibration_gals}")
    if algorithm == 0:
        print(f"Learning rates = {learning_rate0}/{learning_rate_cali}")
    print(f"{num_EAZY_as_dict} of 7 EAZY templates used as initialized dictionaries")
    print(f"Add fluctuations: {add_fluctuations} (x{flux_fluctuation_scaling})")
    # print(f"Data is f_lambda: {data_is_flambda}")


# Read input file and get all necessary information
ztrue, lamb_obs, spec_obs, spec_obs_original, err_obs, rescale_factor = fx.read_file(filename, Ndat=Ndat, 
                                    rescale_constant=rescale_constant, error_method=error_method, 
                                    SNR=SNR, f_lambda_mode=f_lambda_mode, rescale_input=rescale_input, 
                                    add_fluctuations=add_fluctuations, flux_fluctuation_scaling=flux_fluctuation_scaling, template_scale=template_scale)





# For saving files, if using error_method=0, change SNR to a string for filenames
# but if input file doesn't have error column, switch to method 1 and use input SNR
if error_method == 0:
    try:
        np.load(filename)['error']
        print(f"Error method: Original")
        SNR = 'dat'
    except:
        print(f"Error column not found, switch to Error method 1 (SNR={SNR})")
else:
    print(f"Error method: {error_method} (SNR={SNR})")

print('')


# preparing to initialize dictionaries with lamb_rest and EAZY templates
lamb_rest = np.arange(0.01,6.0,0.01)
if eazy_templates_location[-1] != '/':
    eazy_templates_location = eazy_templates_location + '/'
templates_EAZY = fx.load_EAZY(lamb_rest, eazy_templates_location)
if not f_lambda_mode:
    templates_EAZY = fx.flambda2fnu(lamb_rest*10000, templates_EAZY)

# initialize dictionaries
D_rest = fx.initialize_dicts(Ndict, dictionary_fluctuation_scaling=dictionary_fluctuation_scaling, templates_EAZY=templates_EAZY, 
                             num_EAZY_as_dict=num_EAZY_as_dict, lamb_rest=lamb_rest, template_scale=template_scale)
D_rest_initial = D_rest.copy()


# Nfilt = lamb_obs.shape[0]
# Read SPHEREx filters
# Nfilt, filt_length, filt_norm, filt_all_lams, filt_all_lams_reshaped = read_filters(filter_location)
# filter_infos = (Nfilt, filt_length, filt_norm, filt_all_lams, filt_all_lams_reshaped)  # pack them as a tuple to make code a bit cleaner
if filter_location[-1] != '/':
    filter_location = filter_location + '/'
filter_infos = fx.read_filters(filter_location)


tic = time.time()

Ngal = len(ztrue)

# assume as a calibration we are given the true redshifts of some well-studied reference galaxies
# select these at random and rescale the best-fit redshifts by this at the end of each iteration
if fix_calibration_gals:
    i_calibrator_galaxies = i_calibrator_galaxies_input
else:
    rng = default_rng()
    i_calibrator_galaxies = rng.choice(Ngal,size=Ncalibrators,replace=False)


# def main():
if __name__ == "__main__":
    # iterate over the data several times
    Niterations = 3
    # resid_array = np.zeros(Niterations+1)

    A = np.zeros((Ndict+1, Ndict+1))
    B = np.zeros((len(lamb_rest), Ndict+1))


    for i_iter in range(Niterations):
        print(str(i_iter)+' of '+str(Niterations)+' iterations')
        #resid = np.subtract(spec_obs[:],model) # sean commented these out, let's fix these later?
        #resid_array[i_iter] = np.abs(np.sum(resid))
        # go over the calibrator galaxies first N times to get some higher-quality dictionary updates first
        # then go over all the galaxies
        galaxies_to_evaluate = np.append(np.tile(i_calibrator_galaxies,Niterations),np.arange(Ngal).astype('int'))
        for i_gal in galaxies_to_evaluate:
            # update with number of galaxies processed
            if np.mod(i_gal,100)==0 and i_gal not in i_calibrator_galaxies:
                print('    '+str(i_gal)+' of '+str(Ngal)+' spectra')

            # if this is a calibrator galaxy
            if i_gal in i_calibrator_galaxies:
                # use the known redshift
                # zinput = float(ztrue[i_gal])#[0]
                zinput = ztrue[i_gal][0]
            else:
                # otherwise perform a best-fit for the redshift
                zinput = False

            # fit this spectrum and obtain the redshift
            # z,zlow,zhigh,params,model,ztrials,residues = fx.fit_spectrum(lamb_obs, spec_obs[i_gal,:], err_obs[i_gal,:], lamb_rest, D_rest, zgrid=zgrid, filter_infos=filter_infos,
            #                                         zgrid_searchsize=zgrid_searchsize, zgrid_errsearchsize=zgrid_errsearchsize, z_fitting_max=z_fitting_max, probline=probline,
            #                                         zinput=zinput, conv_first=convolve_filter, conv_last=last_stage_convolve_filter,error=False)
            z,zlow,zhigh,params,model,ztrials,residues = fx.fit_spectrum(lamb_obs, spec_obs[i_gal,:], err_obs[i_gal,:], lamb_rest, D_rest, zgrid=zgrid, filter_infos=filter_infos,
                                                    zgrid_searchsize=zgrid_searchsize, zgrid_errsearchsize=zgrid_errsearchsize, z_fitting_max=z_fitting_max, probline=probline,
                                                    zinput=zinput, conv_first=convolve_filter, conv_last=last_stage_convolve_filter, error=False)
            # set the learning rate
            learning_rate = learning_rate0

            # if this is a calibrator galaxy
            if i_gal in i_calibrator_galaxies:
                # use a higher learning rate since we know the redshift is correct
                learning_rate = learning_rate_cali

            # update the spectral dictionary using the residuals between the model and data
            residual = spec_obs[i_gal,:] - model


            # find the rest wavelength range to update
            j_update = np.where((lamb_rest > np.min(lamb_obs)/(1+z)) & (lamb_rest < np.max(lamb_obs)/(1+z)))[0]
            # interpolate the residual to these values
            interpolated_residual = np.interp(lamb_rest[j_update],lamb_obs/(1+z),residual)
            interpolated_spec_obs = np.interp(lamb_rest[j_update], lamb_obs/(1+z), spec_obs[i_gal,:])
            model_rest = ((D_rest).T @ params).reshape(len(lamb_rest))
            model_rest[j_update] = interpolated_spec_obs
            # inspired by the equation below equation 8 in https://dl.acm.org/doi/pdf/10.5555/1756006.1756008
            # update each item in the dictionary (do not modify the DC offset term at the end)

            if algorithm == 0:
                for i in range(D_rest.shape[0]-1):
                    update_factor = learning_rate*(params[i]/(np.sum(params**2)))
                    D_rest[i,j_update] = D_rest[i,j_update] + update_factor*interpolated_residual
            elif algorithm == 1:
                # update A and B
                A += params @ params.T
                B += model_rest.reshape((len(model_rest),1)) @ params.T

                # loop several times for it to converge
                for i in range(N_AB_loops):
                    # update each item in the dictionary (do not modify the DC offset term at the end)
                    for j in range(D_rest.shape[0]-1):
                        uj = 1/np.diagonal(A)[j] * (B[:,j] - (D_rest.T @ A[j])) + D_rest[j]
                        uj_norm = np.linalg.norm(uj)
                        D_rest[j] = uj/max(1, uj_norm)


    print('Provisional Redshift Estimation')
    zbest_provisional = np.zeros(Ngal)
    for i in range(Ngal):
        # update with number of galaxies processed
        if np.mod(i,100)==0:
            print('    '+str(i)+' of '+str(Ngal)+' spectra')
        # fit this spectrum and obtain the redshift
        z,zlow,zhigh,params,model,ztrials,residues = fx.fit_spectrum(lamb_obs, spec_obs[i,:], err_obs[i,:], lamb_rest, D_rest, zgrid=zgrid, filter_infos=filter_infos,
                                                    zgrid_searchsize=zgrid_searchsize, zgrid_errsearchsize=zgrid_errsearchsize, z_fitting_max=z_fitting_max, probline=probline,
                                                    zinput=False, conv_first=convolve_filter, conv_last=last_stage_convolve_filter)
        # store the redshift
        zbest_provisional[i] = z

    # re-iterate on the dictionary using the estimated redshifts 
    # initialize the dictionary again
    D_rest = fx.initialize_dicts(Ndict, dictionary_fluctuation_scaling=dictionary_fluctuation_scaling, templates_EAZY=templates_EAZY, 
                             num_EAZY_as_dict=num_EAZY_as_dict, lamb_rest=lamb_rest, template_scale=template_scale)

    # iterate again

    A = np.zeros((Ndict+1, Ndict+1))
    B = np.zeros((len(lamb_rest), Ndict+1))

    for i_iter in range(Niterations):
        print(str(i_iter)+' of '+str(Niterations)+' re-iterations')
        for i_gal in np.arange(Ngal).astype('int'):
            zinput = zbest_provisional[i_gal]

            # fit this spectrum and obtain the redshift
            z,zlow,zhigh,params,model,ztrials,residues = fx.fit_spectrum(lamb_obs, spec_obs[i_gal,:], err_obs[i_gal,:], lamb_rest, D_rest, zgrid=zgrid, filter_infos=filter_infos,
                                                    zgrid_searchsize=zgrid_searchsize, zgrid_errsearchsize=zgrid_errsearchsize, z_fitting_max=z_fitting_max, probline=probline,
                                                    zinput=zinput, conv_first=convolve_filter, conv_last=last_stage_convolve_filter)
            
            # set the learning rate
            learning_rate = learning_rate0
            # update the spectral dictionary using the residuals between the model and data
            residual = spec_obs[i_gal,:] - model

            # find the rest wavelength range to update
            j_update = np.where((lamb_rest > np.min(lamb_obs)/(1+z)) & (lamb_rest < np.max(lamb_obs)/(1+z)))[0]
            # interpolate the residual to these values
            interpolated_residual = np.interp(lamb_rest[j_update],lamb_obs/(1+z),residual)
            interpolated_spec_obs = np.interp(lamb_rest[j_update], lamb_obs/(1+z), spec_obs[i_gal,:])
            model_rest = ((D_rest).T @ params).reshape(len(lamb_rest))
            model_rest[j_update] = interpolated_spec_obs
            # inspired by the equation below equation 8 in https://dl.acm.org/doi/pdf/10.5555/1756006.1756008
            # update each item in the dictionary (do not modify the DC offset term at the end)
            if algorithm == 0:
                for i in range(D_rest.shape[0]-1):
                    update_factor = learning_rate*(params[i]/(np.sum(params**2)))
                    D_rest[i,j_update] = D_rest[i,j_update] + update_factor*interpolated_residual
            elif algorithm == 1:
                # update A and B
                A += params @ params.T
                B += model_rest.reshape((len(model_rest),1)) @ params.T

                # loop several times for it to converge
                for i in range(N_AB_loops):
                    # update each item in the dictionary (do not modify the DC offset term at the end)
                    for j in range(D_rest.shape[0]-1):
                        uj = 1/np.diagonal(A)[j] * (B[:,j] - (D_rest.T @ A[j])) + D_rest[j]
                        uj_norm = np.linalg.norm(uj)
                        D_rest[j] = uj/max(1, uj_norm)

        
    # plot results
    plt.ion()
    plt.figure(1)
    plt.clf()
    plt.plot(lamb_rest,D_rest.transpose(),'-', alpha=0.8)
    plt.plot(np.nan,np.nan,'k-',label='Trained Template')
    plt.xlabel('Wavelength [um]')
    plt.ylabel('Flux [arb]')
    plt.title('Estimating Redshift Templates from Data')
    plt.legend()
    plt.grid('on')
    plt.tight_layout()
    plt.savefig(output_dirname+f'trained_template_algorithm{algorithm}_SNR{SNR}.png',dpi=600)
    # plt.savefig(output_dirname+'trained_template.png',dpi=600)

    np.savez_compressed(output_dirname+f'trained_template_algorithm{algorithm}_SNR{SNR}.npz',lamb_rest=lamb_rest,D_rest=D_rest)
    # np.savez_compressed(output_dirname+'trained_template.npz',lamb_rest=lamb_rest,D_rest=D_rest)

    # plt.figure(6, figsize=templates_figsize)
    # plt.clf()
    templates_figsize = (6,10)
    tick_fontsize = 6

    fig, axs=plt.subplots(1, 1, figsize=templates_figsize, num=2)
    axs.axis('off')
    for i in range(len(D_rest[:,0])-1):
        plt.subplot(len(D_rest[:,0])-1,1,i+1)
        plt.plot(lamb_rest,D_rest[i,:])
        plt.ylabel(str(i+1))
        plt.grid('on')
        plt.xticks(fontsize=tick_fontsize)
        plt.yticks(fontsize=tick_fontsize)
        ax=plt.gca()
        ax.yaxis.get_offset_text().set_size(tick_fontsize)
    plt.xlabel('Wavelength [um]')
    plt.subplot(len(D_rest[:,0])-1,1,1)
    plt.title('Trained Spectral Type Dictionary')
    plt.tight_layout()
    plt.savefig(output_dirname+f'trained_template_multiplot_algorithm{algorithm}_SNR{SNR}.png',dpi=600)
    # plt.savefig(output_dirname+'trained_template_multiplot.png',dpi=600)


    # fit all galaxies with final template
    print('Final Redshift Estimation')
    zbest_trained = np.zeros(Ngal)
    zlow_trained = np.zeros(Ngal)
    zhigh_trained = np.zeros(Ngal)

    for i in range(Ngal):
        # update with number of galaxies processed
        if np.mod(i,100)==0:
            print('    '+str(i)+' of '+str(Ngal)+' spectra')
        # fit this spectrum and obtain the redshift
        z,zlow,zhigh,params,model,ztrials,residues = fx.fit_spectrum(lamb_obs, spec_obs[i,:], err_obs[i,:], lamb_rest, D_rest, zgrid=zgrid, filter_infos=filter_infos,
                                                    zgrid_searchsize=zgrid_searchsize, zgrid_errsearchsize=zgrid_errsearchsize, z_fitting_max=z_fitting_max, probline=probline,
                                                    zinput=False, conv_first=convolve_filter, conv_last=fitting_convolve_filter, error=True)
        # z,params,model = fit_spectrum(lamb_obs,spec_obs[i,:],lamb_rest,D_rest, conv=True)
        # store the redshift
        zbest_trained[i] = z
        zlow_trained[i] = zlow
        zhigh_trained[i] = zhigh


    # for comparison, fit again with original template
    # turn off this part
    zbest_initial = np.zeros(Ngal)
    # print('Untrained Redshift Estimation')
    # zbest_initial = np.zeros(Ngal)
    # for i in range(Ngal):
    #     # update with number of galaxies processed
    #     if np.mod(i,100)==0:
    #         print('    '+str(i)+' of '+str(Ngal)+' spectra')
    #     # fit this spectrum and obtain the redshift
    #     z,zlow,zhigh,params,model = fit_spectrum(lamb_obs,spec_obs[i,:],err_obs[i,:],lamb_rest,D_rest_initial, conv_first=convolve_filter, conv_last=fitting_convolve_filter, error=False)
    #     # z,params,model = fit_spectrum(lamb_obs,spec_obs[i,:],lamb_rest,D_rest_initial, conv=True)
    #     # store the redshift
    #     zbest_initial[i] = z


    # correct dimsionality of ztrue
    ztrue = ztrue.flatten()

    # find % of catastrophic error and accuracy
    dz = zbest_initial - ztrue
    igood_initial = np.where(np.abs(dz/(1+ztrue)) < 0.15)[0]
    dz = zbest_trained - ztrue
    igood_trained = np.where(np.abs(dz/(1+ztrue)) < 0.15)[0]
    ## standard deviation method
    #accuracy_initial = np.std((zbest_initial[igood_initial] - ztrue[igood_initial])/(1+ztrue[igood_initial]))
    #accuracy_trained = np.std((zbest_trained[igood_trained] - ztrue[igood_trained])/(1+ztrue[igood_trained]))
    # NMAD method
    dz = zbest_initial - ztrue
    accuracy_initial = 1.48*np.median(np.abs((dz-np.median(dz))/(1+ztrue)))
    dz = zbest_trained - ztrue
    accuracy_trained = 1.48*np.median(np.abs((dz-np.median(dz))/(1+ztrue)))
    # note we could switch to nmad 1.48*median((dz-median(dz))/(1+z))
    eta_initial = 100*(Ngal - len(igood_initial))/Ngal
    eta_trained = 100*(Ngal - len(igood_trained))/Ngal


    # plot redshift reconstruction
    zpzs_figsize = (10,10)
    fig1, axs1 = plt.subplots(2,1, figsize=zpzs_figsize, num=3, gridspec_kw={'height_ratios': [3,1]})
    lim_offset = 0.05
    axs1[0].set_xlim(0-lim_offset,2+lim_offset)
    axs1[0].set_ylim(0-lim_offset,2+lim_offset)
    axs1[1].set_ylim(-0.25,0.25)
    axs1[1].set_xlim(0-lim_offset,2+lim_offset)
    axs1[0].grid()
    axs1[1].grid()

    labelfontsize = 18
    tickfontsize = 12
    legendfontsize = 14
    m0 = 'o'
    m1 = 'o'
    m0size = 8
    m1size = 8
    markeredgewidth = 0.3
    # m0edgec = 'tab:blue'
    # m1edgec = 'tab:orange'
    m0edgec = 'k'
    m1edgec = 'k'

    axs1[0].set_ylabel('Estimated Redshift', fontsize=labelfontsize)
    axs1[1].set_xlabel('True Redshift', fontsize=labelfontsize)
    axs1[1].set_ylabel(r'$\Delta z/(1+z_{True})$', fontsize=labelfontsize)
    axs1[0].plot(ztrue, zbest_initial, m0, markersize=m0size, markeredgecolor=m0edgec, markeredgewidth=markeredgewidth, alpha=0.65,
                label=f'Initial, $\eta={eta_initial}$%, $\sigma_{{NMAD}}={100*accuracy_initial:.3f}$%')
    axs1[0].plot(ztrue, zbest_trained, m1, markersize=m1size, markeredgecolor=m1edgec, markeredgewidth=markeredgewidth, alpha=0.8,
                label=f'Trained, $\eta={eta_trained}$%, $\sigma_{{NMAD}}={100*accuracy_trained:.3f}$%')
    axs1[0].plot([0-lim_offset,2+lim_offset],[0-lim_offset,2+lim_offset],'-',alpha=0.8, color='g', linewidth=2)
    axs1[1].plot(ztrue, (zbest_initial-ztrue)/(1+ztrue), m0, markersize=m0size, markeredgecolor=m0edgec, markeredgewidth=markeredgewidth, alpha=0.65)
    axs1[1].plot(ztrue, (zbest_trained-ztrue)/(1+ztrue), m1, markersize=m1size, markeredgecolor=m1edgec, markeredgewidth=markeredgewidth, alpha=0.8)
    axs1[1].plot([0-lim_offset,2+lim_offset],[0,0],'-',alpha=0.8, color='g', linewidth=2)
    axs1[0].tick_params(axis='both', which='major', labelsize=tickfontsize)
    axs1[1].tick_params(axis='both', which='major', labelsize=tickfontsize)
    axs1[0].legend(fontsize=legendfontsize, framealpha=0.9, loc='upper left')
    # axs[1].legend(fontsize=20, loc='lower right')
    fig1.tight_layout()
    plt.savefig(output_dirname+f'redshift_estimation_performance_algorithm{algorithm}_SNR{SNR}.png',dpi=600)
    # plt.savefig(output_dirname+'redshift_estimation_performance.png',dpi=600)


    # save estimated redshifts
    np.savez(output_dirname+'estimated_redshifts.npz',ztrue=ztrue,zest=zbest_trained,zest_initial=zbest_initial,zlow=zlow_trained,zhigh=zhigh_trained,i_cal=i_calibrator_galaxies)

    # for comparison, fit a single spectrum with the initial and trained template
    # select galaxy
    i = 67
    # i = 15
    # refit with the initial dictionary
    zbest_initial_ex,zlow_initial,zhigh_initial,params_initial,best_model_initial,ztrials_initial,residues_initial = fx.fit_spectrum(lamb_obs, spec_obs[i,:], err_obs[i,:], lamb_rest, D_rest_initial, zgrid=zgrid, filter_infos=filter_infos,
                                                    zgrid_searchsize=zgrid_searchsize, zgrid_errsearchsize=zgrid_errsearchsize, z_fitting_max=z_fitting_max, probline=probline,
                                                    zinput=False, conv_first=convolve_filter, conv_last=fitting_convolve_filter)
    # refit with the trained dictionary
    zbest_trained_ex,zlow_trained,zhigh_trained,params_trained,best_model,ztrials_best,residues_best = fx.fit_spectrum(lamb_obs, spec_obs[i,:], err_obs[i,:], lamb_rest, D_rest, zgrid=zgrid, filter_infos=filter_infos,
                                                    zgrid_searchsize=zgrid_searchsize, zgrid_errsearchsize=zgrid_errsearchsize, z_fitting_max=z_fitting_max, probline=probline,
                                                    zinput=False, conv_first=convolve_filter, conv_last=fitting_convolve_filter)
        
    # plot spectrum
    plt.figure(4)
    plt.clf()
    plt.plot(lamb_obs,spec_obs[i,:],'k*',label='Data, ztrue='+str(ztrue[i])[0:5])
    plt.plot(lamb_obs,spec_obs_original[i,:],'b.',label='Data (no noise), ztrue='+str(ztrue[i])[0:5])
    plt.plot(lamb_obs,best_model_initial,label='Initial Template, zest = '+str(zbest_initial_ex))
    plt.plot(lamb_obs,best_model,label='Trained Template, zest = '+str(zbest_trained_ex))
    plt.xlabel('Observed Wavelength [um]')
    plt.ylabel('Flux [arb]')
    plt.legend()
    plt.grid('on')
    plt.tight_layout()
    plt.savefig(output_dirname+f'spectrum_fitting_algorithm{algorithm}_SNR{SNR}.png',dpi=600)
    # plt.savefig(output_dirname+'spectrum_fitting.png',dpi=600)




    # compare learned template with input template
    # create main wavelength array
    lamb_um = np.arange(0.3,4.8,0.01)
    h_lamb_um = (lamb_rest>=min(lamb_um)) & (lamb_rest<max(lamb_um))
    # If we ever need different templates to reconstruct, use following lines
    # templates_EAZY = load_EAZY(lamb_um, eazy_templates_location)
    # if not f_lambda_mode:
    #     templates_EAZY = flambda2fnu(lamb_um*10000, templates_EAZY)

    templates_EAZY = templates_EAZY[:,h_lamb_um]

    D_rest_interpolated_list = []
    for i in range(Ndict+1):
        D_rest_interpolated_list.append(np.interp(lamb_um,lamb_rest,D_rest[i,:]))
    D_rest_interpolated = np.vstack(tuple(D_rest_interpolated_list))

    plt.figure(num=5, figsize=templates_figsize)
    for i in range(7):
        # reconstruct this ground-truth template item with the learned template
        # params =  inv(D*D')*D*s'
        params = np.matmul(np.matmul(np.linalg.inv(np.matmul(D_rest_interpolated,D_rest_interpolated.transpose())),D_rest_interpolated),templates_EAZY[i,:])

        # evaluate model
        this_model = np.zeros_like(lamb_um)
        for j in range(Ndict+1):
            this_model += params[j]*D_rest_interpolated[j,:]
        
        # make a plot
        plt.subplot(7,1,i+1)
        plt.plot(lamb_um,templates_EAZY[i,:],'.',label='Ground-Truth')
        plt.plot(lamb_um,this_model,label='Learned')
        plt.ylabel('T'+str(i))
        plt.grid('on')
        plt.xticks(fontsize=tick_fontsize)
        plt.yticks(fontsize=tick_fontsize)
        ax=plt.gca()
        ax.yaxis.get_offset_text().set_size(tick_fontsize)

    plt.xlabel('[um]')
    plt.subplot(7,1,1)
    plt.title('Reconstructing Ground-Truth Template with Learned Template')
    plt.tight_layout()
    plt.legend()
    plt.savefig(output_dirname+'reconstructing_ground_truth_template.png',dpi=600)

    print('Elapsed Time = '+str(time.time()-tic)+' seconds')

    np.savez(output_dirname+'fluctuated_input_cat.npz', z=ztrue.reshape(Ndat,1), wavelengths=lamb_obs, spectra=spec_obs, error=err_obs, spectra_original=spec_obs_original)

    # np.savez(output_dirname+'min_chi2_dz.npz', chi2=chisqs, zhl=zhl, dz=delta_z, diff=model_diff, rescale_factor=rescale_factor, peak=peak)

