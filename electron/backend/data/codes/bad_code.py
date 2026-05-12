def f(x,y,z):
    a=x+y+z
    if a>10:
        if a<20:
            if a%2==0:
                return a
            else:
                return a+1
        else:
            return a-1
    else:
        return 0
def main():
    for i in range(100):
        for j in range(100):
            for k in range(100):
                f(i,j,k)
main()