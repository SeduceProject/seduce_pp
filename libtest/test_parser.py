from glob import glob
import json, os

json_dir = '../article/paper_results/RPI4_32'

if __name__ == "__main__":
    node_results = {}
    jsonff = glob("%s/*.json" % json_dir)
    jsonff = sorted(jsonff, key=lambda x:int(os.path.basename(x).split('_')[0]))
    for f in jsonff:
        with open(f, 'r') as jsonfile:
            data = json.load(jsonfile)
            print("Read %s with %d environment(s)" % (os.path.basename(f), len(data.keys())))
            for env in data.keys():
                for node in data[env].keys():
                    for node_info in data[env][node]:
                        if node not in node_results:
                            node_results[node] = {}
                        if env not in node_results[node]:
                            node_results[node][env] = {}
                        deployment_size = len(data[env].keys())
                        if deployment_size not in node_results[node][env]:
                            node_results[node][env][deployment_size] = {
                                    'times': [], 
                                    'failed': 0, 'completed': 0
                                }
                        node_stat = node_results[node][env][deployment_size]
                        if node_info['states']['last_state'] == 'deployed':
                            node_stat['times'].append(node_info['total'])
                            node_stat['completed'] += 1
                        else:
                            node_stat['failed'] += 1
    paper_results = {}
    for node in node_results:
        for env in node_results[node]:
            for nb_nodes in node_results[node][env]:
                node_stat = node_results[node][env][nb_nodes]
                if nb_nodes not in paper_results:
                    paper_results[nb_nodes] = {
                            'avg_times': [],
                            'failed': [],
                            'completed': []
                    }
                paper_results[nb_nodes]['failed'].append(node_stat['failed'])
                paper_results[nb_nodes]['completed'].append(node_stat['completed'])
                if len(node_stat['times']) > 0:
                    node_stat['min'] = min(node_stat['times'])
                    node_stat['max'] = max(node_stat['times'])
                    node_stat['avg'] = sum(node_stat['times']) / len(node_stat['times'])
                    paper_results[nb_nodes]['avg_times'].append(node_stat['avg'])

    for result in paper_results.values():
        result['failure_ratio'] = round(sum(result['failed']) * 100 / sum(result['completed']), 2)
        del result['failed']
        del result['completed']
        result['avg_times'] = round(sum(result['avg_times']) / len(result['avg_times']))

    for node in node_results:
        for env in node_results[node]:
            for nb_nodes in node_results[node][env]:
                node_results[node][env][nb_nodes]['usual_time'] = paper_results[nb_nodes]['avg_times']
                node_results[node][env][nb_nodes]['failure_ratio'] = paper_results[nb_nodes]['failure_ratio']
    print(json.dumps(node_results, indent=4))
    print("###### PAPER RESULTS #######")
    print(json.dumps(paper_results, indent=4))
