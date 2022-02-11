import numpy as np
import matplotlib.pyplot as plt

# -----POLYNOMIAL FIT----
x = np.arange(1, 6)  # x coordinates
y = np.array([3, 0, 0, 0, 3])  # y coordinates

fig = plt.figure()
ax = fig.add_subplot(1, 1, 1)

# y = np.array(tuple(map(lambda x: x / 40, y)))

p = np.poly1d(np.polyfit(x, y, deg=9))

xx = np.linspace(0, 6, 500)

ax.set_xlim(0, 6)
# plt.ylim(-0.25, 0.25)
ax.set_ylim(-10, 10)
ax.grid(True)

ax.set_xticks(np.arange(0, 6))
ax.set_yticks(np.arange(-10, 11, 1))
ax.set_yticks(np.arange(-10, 10.5, 0.5), minor=True)

plt.scatter(x, y)
plt.plot(xx, p(xx))
plt.show()

'''
294.36%
194.80%

722.50 
829.00 
'''
