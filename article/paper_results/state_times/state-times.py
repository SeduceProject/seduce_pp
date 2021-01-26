from glob import glob
import json, os

JSON_DIR="../article/paper_results"


def format_name(state_name):
    st = state_name.split('_')
    if len(st) == 1:
        return st[0][:3]
    name = ""
    if len(st) == 2:
        for s in st:
            name += s[:2]
        return name
    if len(st) == 3:
        for s in st:
            name += s[:1]
        return name


times = {}
state_names = []

for dirname in sorted(os.listdir(JSON_DIR), reverse=True):
    if os.path.isdir("%s/%s" % (JSON_DIR, dirname)):
        print(dirname)
        for nb_node in [ 4, 8, 12, 16, 20 ]:
            json_files = glob("%s/%s/%d_*.json" % (JSON_DIR, dirname, nb_node))
            for f in json_files:
                with open(f, "r") as jsonfile:
                    data = json.load(jsonfile)
                for node in data:
                    for name in data[node]:
                        for info in data[node][name]:
                            for state in info["states"]:
                                if isinstance(info["states"][state], float):
                                    if nb_node not in times:
                                        times[nb_node] = {}
                                    if dirname not in times[nb_node]:
                                        times[nb_node][dirname] = {}
                                    time_info = times[nb_node][dirname]
                                    if state not in state_names:
                                        state_names.append(state)
                                    if state not in time_info:
                                        time_info[state] = { "values": [], "nb_exp": len(json_files) }
                                    time_info[state]["values"].append(info["states"][state])

for nb_node in times:
    for expname in times[nb_node]:
        for state in times[nb_node][expname]:
            time_info = times[nb_node][expname][state]
            time_info["avg"] = round(sum(time_info["values"]) / len(time_info["values"]))
            time_info["nb"] = len(time_info["values"])
            del time_info["values"]
print(json.dumps(times, indent=4))

state_names.remove("off_requested")
for nb_node in times:
    with open("%d_states.txt" % nb_node, "w") as txtfile:
        txtfile.write("%s\n" % ";".join([format_name(s) for s in state_names]))
        for expname in times[nb_node]:
            state_times = ""
            for state in state_names:
                if state in times[nb_node][expname]:
                    if state == "rebooting":
                        state_times += "%f;" % (times[nb_node][expname][state]["nb"] /
                                times[nb_node][expname][state]["nb_exp"])
                    else:
                        state_times += "%d;" % times[nb_node][expname][state]["avg"]
                else:
                    state_times += "1000;"
            print("%s: %s" % (expname, state_times))
            txtfile.write("%s\n" % state_times[:-1])


