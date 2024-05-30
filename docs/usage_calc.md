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