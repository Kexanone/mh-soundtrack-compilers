from scipy.io.wavfile import read
import matplotlib.pyplot as plt
plt.rcParams["figure.figsize"] = [7.50, 3.50]
plt.rcParams["figure.autolayout"] = True
input_data = read("out.wav")
audio = input_data[1]
plt.figure()
for track in audio.T:
    plt.plot(track)
plt.ylabel("Amplitude")
plt.xlabel("Time")
plt.show()