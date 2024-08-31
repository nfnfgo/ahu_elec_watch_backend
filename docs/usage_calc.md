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

## Spreading Config

There are 2 config value relevant to _Data Point Spreading_.

- `POINT_SPREADING_DIS_LIMIT_MIN`
- `POINT_SPREADING_DIS_TOLERANCE`

**`POINT_SPREADING_DIS_LIMIT_MIN`**

This config value is used to decide the theoretically minimum time distance between two adjacent points to trigger
_Point Spreading_ operation. For example, if this value is `60`, then any point that have larger than 60 minutes
distance from its previous point should be spread.

Also, this value will be used as the **distance between the spread points**. For example, if a point has been spread to
3 different points, then the distance between this 3 points will all be `POINT_SPREADING_DIS_LIMIT_MIN` minutes.

**`POINT_SPREADING_DIS_TOLERANCE`**

Only considering the previous parameter could cause issue,
when the **distance between two adjacent points are slightly larger than the distance limit**,
the point will be spread to two new points, but actually it **doesn't need to be spread**.
Check out the example below:

```
[0min, 1.5]
[30min1sec, 2.0]
```

Then the second point will be spread to two new points:

```
[0min, 1.5]
[0min1sec, 1.0]   <--- Really close to the first point after spreading.
[30min1sec, 1.0]
```

Obviously we don't want this result.

So we decided to **adding a tolerance when checking if a point need to be spread**.
Now only the point that have distance larger then `POINT_SPREADING_DIS_LIMIT_MIN + POINT_SPREADING_DIS_TOLERANCE`
would trigger Data Point Spreading operation.
Notice the **distance between spread point won't be affected by tolerance**.

For example if the tolerance is `5min`, then only a distance larger than `min_dis + tolerance = 35`
will trigger the spreading. And the distance between newly spread point is still `min_dis = 30`

# Smart Point Merge

When requesting the records of a long time range. _(For example request the usage info of last week)_, the points will
become large in numbers, and which will **cause bad visual effect when show all these point on diagram.**

To solve this issue, we may need to merge usage point when possible. For example, if there are 3 points:

```
Usage Info: [timestamp, usage/hour]
[1, 100]
[2, 500]
[3, 300]
```

Then, if we merged it into one point, it would be:

```
[3, 300]
```

## Timestamp Of The New Point

Currently, the **timestamp of the latest point being merged** would be used as the timestamp of the new point. In this case, the usage statistics may has some delay compared to reality.

## Value Of The New Point

If `usage_pre_hour` is `enabled`, we could simply using the **average value of all the points as the new value**.
However, this may not be so accurate, since the **distance of this three points may not be the same**,
and we should consider the **point with longer distance before it has a larger weight** when calculating average.

If `usage_pre_hour` is `disabled`, we could accumulate all the usage value of the old points to get a completely correct new value for the merged point.

## Merge Ratio

We now need to decide how many points should be merged into a new single point.

Here I decided to use daily usage as pivot. This means, the density will be the same as the daily diagram with
original density.

For example, if there are `24` points per day _(which means catch frequency is 2 times an hour)_, then we should
merge `3` points into one when user requesting a _3 Days_ period usage to keep a `24` point per view density standard.

# Unit Converting

We may want to **convert the unit to Usage/Hour** when output the final usage list.
In this case, the new point value could be calculate using following approach.

```
timestamp_distance = timestamp_this_point - timestamp_prev_point
hour_distance = timestamp_distance / (60 * 60)
new_usage_value = prev_value / hour_distance
```

`time_distance` is the **time distance between current usage point and the previous usage point** before this point. The **unit should be converted to hours**.

----

For example, we have two points:

```
1: {timestamp: 0,    usage: 23.00}
2: {timestamp: 7200, usage: 60.00}
```

> Notice that the usage data structure has been simplified.

In this case, the `hour_distance` would be:

```
hour_distance = 7200 / (60*60)
              = 7200 / 3600
              = 2
```

Then the new value:

```
new_value = prev_value / hour_distance
          = 60.00 / 2
          = 30.00 (Unit: kWh/Hour)
```

> Notice that for **first point** in usage list, we **couldn't convert the unit** for it, 
> since we **don't know the distance between that point and its previous point**.

