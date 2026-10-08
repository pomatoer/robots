#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
mini-Scheme 解释器（符合 spec.md）
入口：src/main.py
"""

import sys
import operator

# ======================================================================
# 1. 数据类型
# ======================================================================

class Symbol:
    """符号：变量名、函数名、关键字等。独立于 str，避免和字符串混淆。"""
    __slots__ = ('name',)
    def __init__(self, name):
        self.name = name
    def __repr__(self):
        return self.name
    def __eq__(self, other):
        return isinstance(other, Symbol) and self.name == other.name
    def __hash__(self):
        return hash(('sym', self.name))


class String:
    """字符串字面量。独立于 Python str，避免和 Symbol 混淆。"""
    __slots__ = ('value',)
    def __init__(self, value):
        self.value = value
    def __repr__(self):
        return '"' + self.value + '"'


class NilType:
    """空表 () 的单例。"""
    __slots__ = ()
    def __repr__(self):
        return '()'


NIL = NilType()


class Pair:
    """点对。列表 (1 2 3) 就是 (1 . (2 . (3 . ()))) 的简写。"""
    __slots__ = ('car', 'cdr')
    def __init__(self, car, cdr):
        self.car = car
        self.cdr = cdr
    def __repr__(self):
        return to_string(self)


class Procedure:
    """用户定义过程（闭包）：记住形参、函数体、定义时的环境。"""
    __slots__ = ('params', 'body', 'env')
    def __init__(self, params, body, env):
        self.params = params      # list[Symbol]
        self.body = body          # list[expr]
        self.env = env            # 定义处的环境（词法作用域关键）


class BuiltinProcedure:
    """内置过程，func 接受 args 列表，返回一个值。"""
    __slots__ = ('func', 'name')
    def __init__(self, func, name='#<builtin>'):
        self.func = func
        self.name = name


# ======================================================================
# 2. 环境
# ======================================================================

class Environment:
    """变量绑定表 + 外层指针。"""
    __slots__ = ('parent', 'bindings')
    def __init__(self, parent=None):
        self.parent = parent
        self.bindings = {}

    def lookup(self, symbol):
        env = self
        while env is not None:
            if symbol.name in env.bindings:
                return env.bindings[symbol.name]
            env = env.parent
        raise SchemeError(f'unbound symbol: {symbol.name}')

    def define(self, symbol, value):
        self.bindings[symbol.name] = value


class SchemeError(Exception):
    pass


# ======================================================================
# 3. 词法分析：文本 -> token 列表
# ======================================================================

DELIMS = set('()\';"')

def tokenize(text):
    tokens = []
    i, n = 0, len(text)
    while i < n:
        c = text[i]
        if c.isspace():
            i += 1
        elif c == ';':
            while i < n and text[i] != '\n':
                i += 1
        elif c in '()':
            tokens.append(c)
            i += 1
        elif c == "'":
            tokens.append("'")
            i += 1
        elif c == '"':
            i += 1
            chars = []
            while i < n and text[i] != '"':
                if text[i] == '\\':
                    i += 1
                    if i >= n:
                        raise SchemeError('unterminated string')
                    esc = text[i]
                    chars.append({'n': '\n', 't': '\t',
                                  '"': '"', '\\': '\\'}.get(esc, esc))
                else:
                    chars.append(text[i])
                i += 1
            if i >= n:
                raise SchemeError('unterminated string')
            i += 1  # 跳过收尾引号
            tokens.append(String(''.join(chars)))
        else:
            start = i
            while i < n and not text[i].isspace() and text[i] not in DELIMS:
                i += 1
            atom = text[start:i]
            if atom == '#t':
                tokens.append(True)
            elif atom == '#f':
                tokens.append(False)
            else:
                try:
                    tokens.append(int(atom))
                except ValueError:
                    try:
                        tokens.append(float(atom))
                    except ValueError:
                        tokens.append(Symbol(atom))
    return tokens


# ======================================================================
# 4. 语法分析：token -> 嵌套表达式
# ======================================================================

def parse(tokens):
    if not tokens:
        raise SchemeError('unexpected EOF')
    tok = tokens.pop(0)
    if tok == '(':
        lst = []
        while tokens and tokens[0] != ')':
            lst.append(parse(tokens))
        if not tokens:
            raise SchemeError('missing )')
        tokens.pop(0)
        return lst
    if tok == "'":
        return [Symbol('quote'), parse(tokens)]
    if tok == ')':
        raise SchemeError('unexpected )')
    return tok


# ======================================================================
# 5. 打印：值 -> 文本
# ======================================================================

def to_string(val, display=False):
    if val is None:
        return ''
    if val is True:
        return '#t'
    if val is False:
        return '#f'
    if isinstance(val, int):
        return str(val)
    if isinstance(val, float):
        return repr(val)
    if isinstance(val, Symbol):
        return val.name
    if isinstance(val, String):
        if display:
            return val.value
        esc = (val.value
               .replace('\\', '\\\\')
               .replace('"', '\\"')
               .replace('\n', '\\n')
               .replace('\t', '\\t'))
        return '"' + esc + '"'
    if val is NIL:
        return '()'
    if isinstance(val, Pair):
        parts = []
        cur = val
        while isinstance(cur, Pair):
            parts.append(to_string(cur.car, display))
            cur = cur.cdr
        if cur is NIL:
            return '(' + ' '.join(parts) + ')'
        if not parts:
            return '(' + to_string(cur, display) + ')'
        return '(' + ' '.join(parts) + ' . ' + to_string(cur, display) + ')'
    if isinstance(val, (Procedure, BuiltinProcedure)):
        return '#<procedure>'
    return str(val)


# ======================================================================
# 6. 辅助
# ======================================================================

def quote_to_data(expr):
    """把 parse 出来的 Python list 转成点对链。"""
    if isinstance(expr, list):
        result = NIL
        for item in reversed(expr):
            result = Pair(quote_to_data(item), result)
        return result
    return expr


def list_from_py(items):
    result = NIL
    for item in reversed(items):
        result = Pair(item, result)
    return result


def py_from_list(lst, allow_improper=False):
    """把点对链转成 Python list；如果不允许非真列表则报错。"""
    out = []
    cur = lst
    while isinstance(cur, Pair):
        out.append(cur.car)
        cur = cur.cdr
    if cur is not NIL and not allow_improper:
        raise SchemeError('expected proper list')
    return out, cur


# ======================================================================
# 7. 求值器：evaluate 与 apply 互相调用
# ======================================================================

def eval_begin(exprs, env):
    result = None
    for e in exprs:
        result = eval_expr(e, env)
    return result


def eval_expr(expr, env):
    # 符号 -> 查环境
    if isinstance(expr, Symbol):
        return env.lookup(expr)
    # 基本值 -> 原样返回
    if expr is NIL or expr is None:
        return expr
    if expr is True or expr is False:
        return expr
    if isinstance(expr, (int, float, String)):
        return expr
    # 列表表达式
    if isinstance(expr, list):
        if not expr:
            raise SchemeError('cannot evaluate ()')
        head = expr[0]
        if isinstance(head, Symbol):
            name = head.name
            if name == 'quote':
                return quote_to_data(expr[1])
            if name == 'if':
                if eval_expr(expr[1], env) is not False:
                    return eval_expr(expr[2], env)
                return eval_expr(expr[3], env) if len(expr) > 3 else None
            if name == 'cond':
                for clause in expr[1:]:
                    test = clause[0]
                    if isinstance(test, Symbol) and test.name == 'else':
                        return eval_begin(clause[1:], env)
                    val = eval_expr(test, env)
                    if val is not False:
                        if len(clause) == 1:
                            return val
                        return eval_begin(clause[1:], env)
                return None
            if name == 'and':
                if len(expr) == 1:
                    return True
                val = True
                for e in expr[1:]:
                    val = eval_expr(e, env)
                    if val is False:
                        return False
                return val
            if name == 'or':
                if len(expr) == 1:
                    return False
                for e in expr[1:]:
                    val = eval_expr(e, env)
                    if val is not False:
                        return val
                return False
            if name == 'define':
                target = expr[1]
                if isinstance(target, Symbol):
                    value = eval_expr(expr[2], env)
                    env.define(target, value)
                    return target
                if isinstance(target, list):
                    fname = target[0]
                    params = target[1:]
                    body = expr[2:]
                    env.define(fname, Procedure(params, body, env))
                    return fname
                raise SchemeError('invalid define')
            if name == 'lambda':
                return Procedure(expr[1], expr[2:], env)
            if name == 'let':
                bindings = expr[1]
                body = expr[2:]
                # 并行：先把所有绑定值在外层求出来
                pairs = [(b[0], eval_expr(b[1], env)) for b in bindings]
                new_env = Environment(env)
                for sym, val in pairs:
                    new_env.define(sym, val)
                return eval_begin(body, new_env)
            if name == 'begin':
                return eval_begin(expr[1:], env)
        # 函数调用：先求操作符和实参，再 apply
        proc = eval_expr(head, env)
        args = [eval_expr(a, env) for a in expr[1:]]
        return apply_proc(proc, args)

    raise SchemeError(f'cannot evaluate: {expr!r}')


def apply_proc(proc, args):
    if isinstance(proc, BuiltinProcedure):
        return proc.func(args)
    if isinstance(proc, Procedure):
        if len(args) != len(proc.params):
            raise SchemeError(
                f'arity mismatch: expected {len(proc.params)}, got {len(args)}')
        new_env = Environment(proc.env)
        for sym, val in zip(proc.params, args):
            new_env.define(sym, val)
        return eval_begin(proc.body, new_env)
    raise SchemeError(f'not a procedure: {to_string(proc)}')


# ======================================================================
# 8. 内置库（spec §5）
# ======================================================================

def _int_div(a, b):
    """整数除法，商向零截断。"""
    q = abs(a) // abs(b)
    return -q if (a < 0) != (b < 0) else q


def standard_env():
    env = Environment()

    def reg(name, fn):
        env.define(Symbol(name), BuiltinProcedure(fn, name))

    # ---------- 算术 ----------
    reg('+', lambda args: sum(args))

    def sub(args):
        if len(args) == 1:
            return -args[0]
        r = args[0]
        for x in args[1:]:
            r -= x
        return r
    reg('-', sub)

    def mul(args):
        r = 1
        for x in args:
            r *= x
        return r
    reg('*', mul)

    def div(args):
        if len(args) == 1:
            return 1 / args[0]
        r = args[0]
        for x in args[1:]:
            if isinstance(r, int) and isinstance(x, int):
                r = _int_div(r, x)
            else:
                r = r / x
        return r
    reg('/', div)

    reg('modulo', lambda args: args[0] % args[1])
    reg('quotient', lambda args: _int_div(args[0], args[1]))
    reg('expt', lambda args: args[0] ** args[1])
    reg('abs', lambda args: abs(args[0]))

    # ---------- 比较（链式）----------
    def chain(op):
        def cmp(args):
            for a, b in zip(args, args[1:]):
                if isinstance(a, Symbol) and isinstance(b, Symbol):
                    if not op(a.name, b.name):
                        return False
                elif isinstance(a, (int, float)) and not isinstance(a, bool) \
                        and isinstance(b, (int, float)) and not isinstance(b, bool):
                    if not op(a, b):
                        return False
                else:
                    return False
            return True
        return cmp
    reg('=',  chain(operator.eq))
    reg('<',  chain(operator.lt))
    reg('>',  chain(operator.gt))
    reg('<=', chain(operator.le))
    reg('>=', chain(operator.ge))

    # ---------- 布尔 ----------
    reg('not', lambda args: args[0] is False)

    # ---------- 列表 ----------
    reg('cons', lambda args: Pair(args[0], args[1]))

    def car(args):
        if not isinstance(args[0], Pair):
            raise SchemeError('car: not a pair')
        return args[0].car
    reg('car', car)

    def cdr(args):
        if not isinstance(args[0], Pair):
            raise SchemeError('cdr: not a pair')
        return args[0].cdr
    reg('cdr', cdr)

    reg('list', lambda args: list_from_py(args))

    def length(args):
        items, tail = py_from_list(args[0])
        return len(items)
    reg('length', length)

    def append(args):
        if not args:
            return NIL
        result = args[-1]
        for lst in reversed(args[:-1]):
            items, _ = py_from_list(lst)
            for item in reversed(items):
                result = Pair(item, result)
        return result
    reg('append', append)

    reg('null?', lambda args: args[0] is NIL)
    reg('pair?', lambda args: isinstance(args[0], Pair))
    reg('list?', lambda args: py_from_list(args[0], allow_improper=True)[1] is NIL)

    # ---------- 谓词 ----------
    reg('number?',  lambda args: isinstance(args[0], (int, float)) and not isinstance(args[0], bool))
    reg('boolean?', lambda args: isinstance(args[0], bool))
    reg('symbol?',  lambda args: isinstance(args[0], Symbol))
    reg('string?',  lambda args: isinstance(args[0], String))
    reg('procedure?', lambda args: isinstance(args[0], (Procedure, BuiltinProcedure)))
    reg('zero?', lambda args: args[0] == 0)
    reg('even?', lambda args: args[0] % 2 == 0)
    reg('odd?',  lambda args: args[0] % 2 != 0)

    def eq(a, b):
        if isinstance(a, bool) or isinstance(b, bool):
            return a is b
        if isinstance(a, Symbol) and isinstance(b, Symbol):
            return a.name == b.name
        if isinstance(a, String) and isinstance(b, String):
            return a.value == b.value
        if isinstance(a, (int, float)) and isinstance(b, (int, float)):
            return a == b
        return a is b
    reg('eq?', lambda args: eq(args[0], args[1]))

    def equal(a, b):
        if isinstance(a, Pair) and isinstance(b, Pair):
            return equal(a.car, b.car) and equal(a.cdr, b.cdr)
        if a is NIL and b is NIL:
            return True
        if isinstance(a, bool) or isinstance(b, bool):
            return a is b
        if isinstance(a, Symbol) and isinstance(b, Symbol):
            return a.name == b.name
        if isinstance(a, String) and isinstance(b, String):
            return a.value == b.value
        if isinstance(a, (int, float)) and isinstance(b, (int, float)):
            return a == b
        return a is b
    reg('equal?', lambda args: equal(args[0], args[1]))

    # ---------- 输出 ----------
    def display(args):
        sys.stdout.write(to_string(args[0], display=True))
        return None
    reg('display', display)

    def newline(args):
        sys.stdout.write('\n')
        return None
    reg('newline', newline)

    return env


# ======================================================================
# 9. 入口
# ======================================================================

def run_source(text, env):
    tokens = tokenize(text)
    while tokens:
        expr = parse(tokens)
        result = eval_expr(expr, env)
        if result is not None:
            print(to_string(result))


def main():
    env = standard_env()
    args = sys.argv[1:]
    if args:
        for path in args:
            with open(path, 'r', encoding='utf-8') as f:
                run_source(f.read(), env)
    else:
        run_source(sys.stdin.read(), env)


if __name__ == '__main__':
    main()
