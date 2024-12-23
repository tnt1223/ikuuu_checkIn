import pandas as pd
from ortools.sat.python import cp_model

df_raw = pd.read_excel('ikuuu_checkIn/data.xlsx', header=None, usecols=[1])

target = 177797.37
factor = 100
df = df_raw.astype(float) * factor
df[1] = df[1].round().astype(int)
target_sum = int(target * factor)

model = cp_model.CpModel()
var_x = [model.NewIntVar(0, 1, f'x[{i}]') for i in range(len(df))]
df['x'] = var_x

total_obj = (df[1] * df['x']).sum()
model.Add(total_obj <= target_sum)
model.Maximize(total_obj)

solver = cp_model.CpSolver()
status = solver.Solve(model)
if status == cp_model.OPTIMAL:
    print('找到最优解')
    print(f'指定值:{target_sum},目标值: {solver.ObjectiveValue()}')
else:
    print('未找到最优解')

df['result'] = df['x'].apply(solver.Value)
df.drop('x').to_excel('result.xlsx', index=True, header=True)
