# Usage Calculation In Backend

When record data, we actually record the illumination and air conditioner account balance of a specific timestamp.

# Definition Of Usage

Consider two adjacent record:

```
{timestamp: 100, light_balance: 105.5, ac_balance: 50.5}
{timestamp: 200, light_balance: 95.5, ac_balance: 70}
```

## For First Record

If there is no any record before first record, we actually couldn't know the usage statistics at timestamp `100`. So
if we try to convert it from _Balance List_ to _Usage List_, the **usage of the first record will always be zero**.

## Other Records

Now consider the second record. For `light_balance`, since it's desending, the usage will be `105.5 - 95.5 = 10.0`.

But since the `ac_balance` is ascending, we actually don't know the usage of this one, so it would also be set to `0`.

# Data Point Spreading

Sometimes the time between two caught records may be long, which will cause problem when we try using line chart to
show the `usage` data. Which I will use `rag graph` to refer.

To solve this issue, we may need to detect the records with long timestamp distance then deal with such data points.
Here we call the action `Point Spreading`.

First we need to set up the _Maximum Distance_ allowed for two adjacent records, use `max_dis` to represents in
following.

Then if the timestamp distance are greater then the `max_dis`, we will dividing the later record into several new
records with lower usage.

![image.png](https://github.com/NFSandbox/ahu_elec_watch_backend/assets/61616918/9da6f13e-bace-431e-8c77-c5516e3a3713)

As the image shows, consider the distance between two records is `dis`, then the point we need to add is:

```
new_point_count = (dis - 1) / max_dis
```

And we need to update the value of all newly added record (including the original record2).

New value will be `record2.value / (new_point_count + 1)`. Here has a `+1` because we need to take the original
`record2` into consideration.