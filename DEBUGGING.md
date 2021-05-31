### Performance profiling

The deployment may be slow down by one machine. In this case, systemd-analyze is useful
to identify the root cause.

```shell
time vl up
vl ansible_inventory > inventory
ansible all -m shell -a "systemd-analyze blame|head -n 5" -i inventory
```
