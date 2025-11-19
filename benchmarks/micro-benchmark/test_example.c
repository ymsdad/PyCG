typedef struct {
    int x;
    int y;
    int (*func)(int, int);
} Point;

int add(int a, int b) {
    return a + b;
}

Point p;
Point *init(int x, int y) {
    Point *new_point = malloc(sizeof(Point));
    new_point->x = x;
    new_point->y = y;
    new_point->func = add;
    return new_point;
}

int main() {
    Point *p = init(1, 2);
    printf("%d\n", p->func(p->x, p->y));
    return 0;
}
