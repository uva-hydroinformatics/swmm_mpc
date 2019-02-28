import os
import json
import random
import multiprocessing
from deap import base, creator, tools, algorithms
import numpy as np
import evaluate as ev


creator.create('FitnessMin', base.Fitness, weights=(-1.0,))
creator.create('Individual', list, fitness=creator.FitnessMin)

pool = multiprocessing.Pool(16)
toolbox = base.Toolbox()
toolbox.register('map', pool.map)
toolbox.register('attr_binary', random.randint, 0, 10)
toolbox.register('mate', tools.cxTwoPoint)
toolbox.register('mutate', tools.mutUniformInt, low=0, up=10, indpb=0.10)
toolbox.register('select', tools.selTournament, tournsize=6)


def run_ea(ngen, nindividuals, work_dir, hs_file_path,
           inp_process_file_path, sim_dt, control_time_step, n_control_steps,
           control_str_ids, target_depth_dict, node_flood_weight_dict,
           flood_weight, dev_weight):
    toolbox.register('evaluate',
                     ev.evaluate,
                     hs_file_path=hs_file_path,
                     process_file_path=inp_process_file_path,
		     sim_dt=sim_dt,
                     control_time_step=control_time_step,
                     n_control_steps=n_control_steps,
                     control_str_ids=control_str_ids,
                     node_flood_weight_dict=node_flood_weight_dict,
                     target_depth_dict=target_depth_dict,
                     flood_weight=flood_weight,
                     dev_weight=dev_weight
                    )
    policy_len = get_policy_length(control_str_ids, n_control_steps)
    toolbox.register('individual', tools.initRepeat, creator.Individual,
                     toolbox.attr_binary, policy_len)

    # read from the json file to initialize population if exists
    # (not first time)
    pop_file = "{}population.json".format(work_dir)
    if os.path.isfile(pop_file):
        toolbox.register("pop_guess", init_population, creator.Individual, 
                         pop_file)
        pop = toolbox.pop_guess()
    else:
        toolbox.register('population', tools.initRepeat, list,
                         toolbox.individual)
        pop = toolbox.population(n=nindividuals)

    hof = tools.HallOfFame(1)
    stats = tools.Statistics(lambda ind: ind.fitness.values)
    stats.register('avg', np.mean)
    stats.register('min', np.min)
    stats.register('max', np.max)
    pop, logbook = algorithms.eaSimple(pop, toolbox, cxpb=0.5, mutpb=0.2,
                                       ngen=ngen, stats=stats, halloffame=hof,
                                       verbose=True)
    seed_next_population(hof[0], nindividuals, len(control_str_ids), pop_file)
    return hof[0]


def write_pop_to_file(population, pop_file):
    """
    write a population of individuals to json file
    """
    with open(pop_file, 'w') as myfile:
        json.dump(population, myfile) 


def mutate_pop(best_policy, nindividuals, n_controls):
    """
    mutate the best policy of the current time step 
    best_policy:    [list] represents the time series of policies for each 
                    control structure for each time step
    nindividuals:   [int] the number of individuals in a population
    n_controls:     [int] the number of controls in the system
    """
    list_of_inds = []
    for i in range(nindividuals):
	# split because there may be more than one control
	split_lists = split_list(list(best_policy), n_controls)
	mutated_ind = []
	for l in split_lists:
            # disregard the first control step since we need future policy
	    l = l[1:]
            # mutate the remaining settings
            tools.mutUniformInt(l, 0, 10, 0.2)
            # add a random setting for the last time step in the future policy
            l.append(random.randint(0, 10))
            # add the new policy for the control structure to the overall pol
	    mutated_ind.extend(l)
        # don't add the new indivi to the pop if identical indivi already there
        if mutated_ind not in list_of_inds:
            list_of_inds.append(mutated_ind)
    return list_of_inds


def seed_next_population(best_policy, nindividuals, n_controls, pop_file):
    """
    seed the population for the next time step using the best policy from the
    current time step as the basis. The policy 

    """
    mutated_pop = mutate_pop(best_policy, nindividuals, n_controls)

    # in case there were duplicates after mutating, 
    # fill the rest of the population with random individuals 
    while len(mutated_pop) < nindividuals:
        rand_ind = []
        for i in range(len(best_policy)):
            rand_ind.append(random.randint(0, 10))
        if rand_ind not in mutated_pop:
            mutated_pop.append(rand_ind)
    write_pop_to_file(mutated_pop, pop_file)

    return mutated_pop



def init_population(ind_init, filename):
    """
    create initial population from json file
    ind_init:   [class] class that and individual will be assigned to
    filename:   [string] string of filename from which pop will be read
    returns:    [list] list of Individual objects
    """
    with open(filename, "r") as pop_file:
        contents = json.load(pop_file)
    return list(ind_init(c) for c in contents)


def split_list(a_list, n):
    """
    split one list into n lists of equal size. In this case, we are splitting 
    the list that represents all of the policies so that each control structure 
    has its own list
    """
    portions = len(a_list)/n
    split_lists = []
    for i in range(n):
	split_lists.append(a_list[i*portions: (i+1)*portions])	
    return split_lists

def get_policy_length(control_str_ids, n_control_steps):
    """
    get the length of the policy. ASSUMPTION - PUMP controls are binary 1 BIT, 
    ORIFICE and WEIR are 3 BITS
    returns:    [int] the number of total control decisions in the policy
    """
    pol_len = 0
    for ctl_id in control_str_ids:
        ctl_type = ctl_id.split()[0]
        if ctl_type == 'ORIFICE' or ctl_type == 'WEIR':
            pol_len += 3*n_control_steps
        elif ctl_type == 'PUMP':
            pol_len += n_control_steps
    return pol_len

