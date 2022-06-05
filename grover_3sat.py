from qiskit import QuantumCircuit
from qiskit import QuantumRegister
from qiskit import ClassicalRegister
from qiskit import *
from qiskit.visualization import plot_histogram
import matplotlib.pyplot as plt

NUM_VARIABLES = 3
NOT_OPERATOR = "not "
OR_OPERATOR = " or "
AND_OPERATOR = " and "

def print_error(msg):
    """Prints an error message with a specific format
    
    Parameters
    ----------
    msg: str
        the error message
    """
    
    print(f"[ERROR] {msg} Exiting.")


def process(cnf):
    """Processes a cnf in the form of a string

    Parameters
    ----------
    cnf: str
        the cnf to parse

    Returns
    -------
    (list, list)
        the list of used variables (str) and the list of clauses (list) respectively
    """

    # Default variables, changed later when reading the CNF
    input_variables = ["x", "y", "z"]

    used_variables = set()
    # Split the cnf into clauses
    clauses = cnf.split(AND_OPERATOR)
    for i in range(len(clauses)):
        # Split the clause into single variables
        clause_variables = clauses[i].split(OR_OPERATOR)
        for j in range(len(clause_variables)):
            # remove the parentheses
            clause_variables[j] = clause_variables[j].replace(")", "")
            clause_variables[j] = clause_variables[j].replace("(", "")
            # Identify the input variables (can be strings not only characters)
            used_variables.add(clause_variables[j].split(" ")[-1])
            clauses[i] = sorted(clause_variables, key=lambda elem: elem.split("not ")[-1])
    if len(used_variables) != NUM_VARIABLES:
        return (list(used_variables), clauses)
    for i in range(NUM_VARIABLES):
        input_variables[i] = list(used_variables)[i]
    input_variables.sort()
    return (input_variables, clauses)


def check(variables, clauses):
    """Checks that the parsed CNF formula is correct and print an error otherwise

    Parameters
    ----------
    variables: list
        the list of possible variables to use
    clauses: list
        the clauses containing the used variables with possible negations

    Returns
    -------
    int
        0 if there were no errors during the parsing phase, -1 otherwise
    """

    # Check that the CNF formula is valid and conform to the CNF example syntax
    if len(variables) != NUM_VARIABLES or len(clauses) == 0:
        print_error("The CNF formula needs exactly {NUM_VARIABLES} different variables, at least one clause, and must be conform to the example CNF.")
        return -1

    # Check that the number of times a variable is used per clause is exactly 1
    for used_variable in variables:
        for i in range(len(clauses)):
            clause_without_nots = list(map(lambda clause_variable: clause_variable.replace(NOT_OPERATOR, ""), clauses[i]))
            var_count = clause_without_nots.count(used_variable)
            if var_count != 1:
                print_error(f"The number of times a variable must be used per clause must be exactly 1 (got {var_count} for {used_variable} in clause {i+1}).")
                return -1
    return 0


def create_qc_info(variables, clauses):
    """Creates the required information for initializing a quantum circuit
    
    Parameters
    ----------
    variables: list
        the list of variables used in the initial CNF
    clauses: list
        the list of clauses of the initial CNF
        
    Returns
    -------
    (dict, int)
        A mapping of the variables to qubit indices and the number of qubits to use
    """
    
    # variable_name -> qubit index map
    variable_map = {}
    for i in range(NUM_VARIABLES):
        variable_map[variables[i]] = i;
    
    # 3 qubits for the inputs and num_clauses + 1 ancillary qubits
    num_qregs = NUM_VARIABLES + len(clauses) + 1
    return (variable_map, num_qregs)


def create_circuit(num_qregs):
    """Creates an empty circuit with set quantum and classical registers

    Parameters
    ----------
    num_qregs: int
        the number of quantum registers required by the circuit

    Returns
    -------
        QuantumCircuit: the produced empty quantum circuit
    """

    qregs = QuantumRegister(num_qregs,'q')
    cregs = ClassicalRegister(NUM_VARIABLES, 'c')
    circuit = QuantumCircuit(qregs, cregs)
    return circuit


def initialize_circuit(circuit):
    """Initialize a circuit with the |0> state for the inputs and |1> for the ancillary qubits

    Parameters
    ----------
    circuit: QuantumCircuit
        the circuit to initialize
    """

    circuit.reset(circuit.qubits)

    # Add NOT gate to the ancillary qubits
    circuit.x(circuit.qubits[-1])
    circuit.barrier(circuit.qubits)


def prepare_state_superposition(circuit):
    """Preparate a state of superposition for all the qubits ("quantum parallelism")

    Parameters
    ----------
    circuit: QuantumCircuit
        the circuit to initialize
    """

    circuit.h(circuit.qubits[:NUM_VARIABLES])
    circuit.h(circuit.qubits[-1])
    circuit.barrier(circuit.qubits)


def add_3or(circuit, clause_index, clause_qubit_map, negated_map, reverse_circuit):
    """Adds a 3-input OR gate to a circuit

    Parameters
    ----------
    circuit: QuantumCircuit
        the circuit to add the OR gate to
    clause_index: int
        the clause that the or gate corresponds to
    clause_qubit_map: dict
        the map containing which clause maps to which ancillary qubit
    negated_map: dict
        the map keeping track of which qubits are negated in which clause
    """

    circuit.barrier(circuit.qubits)
    for negated_qubit in negated_map[clause_index]:
        circuit.x(circuit.qubits[negated_qubit])
        reverse_circuit.x(reverse_circuit.qubits[negated_qubit])

    circuit.barrier(circuit.qubits)
    reverse_circuit.barrier(reverse_circuit.qubits)
    # Using De Morgan's law
    for i in range(NUM_VARIABLES):
        circuit.x(i)
        reverse_circuit.x(i)

    # Create the multicontrolled-not gate for propagating the value of a or b or c to the corresponding ancilla qubit
    circuit.mcx(list(range(NUM_VARIABLES)), clause_qubit_map[clause_index])
    reverse_circuit.mcx(list(range(NUM_VARIABLES)), clause_qubit_map[clause_index])
    circuit.x(clause_qubit_map[clause_index])
    reverse_circuit.x(clause_qubit_map[clause_index])

    circuit.barrier(circuit.qubits)
    reverse_circuit.barrier(reverse_circuit.qubits)

    # Reverse the negated qubits (due to De Morgan's law) to keep their initial state
    for i in range(NUM_VARIABLES):
        circuit.x(i)
        reverse_circuit.x(i)

    circuit.barrier(circuit.qubits)
    reverse_circuit.barrier(reverse_circuit.qubits)

    # Reverse the negated qubits to keep their initial value
    for negated_qubit in negated_map[clause_index]:
        circuit.x(negated_qubit)
        reverse_circuit.x(negated_qubit)
    circuit.barrier(circuit.qubits)
    reverse_circuit.barrier(reverse_circuit.qubits)


def add_and(circuit):
    """Adds a 3-input AND gate to a circuit

    Parameters
    ----------
    circuit: QuantumCircuit
        the circuit to add the AND gate to
    """
    circuit.barrier(circuit.qubits)
    circuit.mcx(list(range(NUM_VARIABLES, circuit.num_qubits-1)), circuit.num_qubits-1)
    circuit.barrier(circuit.qubits)


def add_uf(circuit, variable_map, variables, clauses, reverse_circuit):
    """Adds the unitary U_f (the boolean function itself) to the circuit

    Parameters
    ----------
    circuit: QuantumCircuit
        the circuit to add U_f to
    variable_map: dictimport re
        the map that stores which variable maps to which qubit (index)
    variables: list
        the used variables in the CNF
    clauses: list
        the clauses of the CNF
    """

    # Map the clauses to the ancillary qubits (the last qubit will store the overall result)
    clause_qubit_map = {}
    for i in range(len(clauses)):
        clause_qubit_map[i] = circuit.qubits[NUM_VARIABLES + i]

    # clause index -> list of qubits that should be negated
    negated_map = {}

    # Create the circuit
    for i in range(len(clauses)):
        # Check which variables are negated
        negated_variables = filter(lambda variable: variable.startswith(NOT_OPERATOR), clauses[i])
        # We know which variables are negated so we can remove the "not " from them by splitting the string and taking the second element
        negated_variables = map(lambda variable: variable.split(" ")[1], negated_variables) # Change to 1
        # Retrieve the correponding qubit index for each variable in the negated variables
        negated_map[i] = sorted(list(map(lambda negated_variable: variable_map[negated_variable], negated_variables)))

        # For each clause we can now create the appropriate quantum gates that corresponds to that clause
        add_3or(circuit, i, clause_qubit_map, negated_map, reverse_circuit)

    add_and(circuit)
    circuit.barrier(circuit.qubits)



def prepare_circuit(variables, clauses, initialize=True):
    """Prepares a circuit from known paramteres

    Parameters
    ----------
    variables: list
        the list of variables used in the CNF
    clauses: list
        the list of clauses used in the CNF

    Returns
    -------
    circuit: QuantumCircuit
        the prepared circuit
    """
    (variable_map, num_qregs) = create_qc_info(variables, clauses)
    circuit = create_circuit(num_qregs)
    if initialize:
        initialize_circuit(circuit)
    return circuit



def add_reflector(circuit):
    """Adds the reflector operator to 3-qubit circuit

    Parameters
    ----------
    circuit: QuantumCircuit
        the circuit to add the reflector to
    """

    circuit.barrier(circuit.qubits)
    circuit.h(circuit.qubits[:NUM_VARIABLES])
    circuit.x(circuit.qubits[:NUM_VARIABLES])
    circuit.barrier(circuit.qubits[:NUM_VARIABLES])
    circuit.h(circuit.qubits[2])
    circuit.ccx(circuit.qubits[0], circuit.qubits[1], circuit.qubits[2])
    circuit.h(circuit.qubits[2])
    circuit.barrier(circuit.qubits[:NUM_VARIABLES])
    circuit.x(circuit.qubits[:NUM_VARIABLES])
    circuit.h(circuit.qubits[:NUM_VARIABLES])
    circuit.barrier(circuit.qubits)


def build_grover(variables, clauses):
    """Builds Grover's box
    
    Parameters
    ----------
    variables: list
        the list of variables used in the CNF
    clauses: list
        the list of clauses used in the CNF
        
    Returns
    -------
    QuantumCircuit
        the produced Grover's box
    """
    
    reverse_circuit = prepare_circuit(variables, clauses, initialize=False) # Reversing U_f's operations
    
    (variable_map, num_qregs) = create_qc_info(variables, clauses)
    circuit = create_circuit(num_qregs)
    add_uf(circuit, variable_map, variables, clauses, reverse_circuit)
    reversed_circuit = reverse_circuit.inverse()
    circuit = circuit.compose(reversed_circuit) # Invert the previous transformations except the "and" operation
    add_reflector(circuit)
    return circuit


def measure_circuit(circuit):
    """Adds a z-basis measurement operations to a circuit

    Parameters
    ----------
    circuit: QuantumCircuit
        the circuit to measure
    """

    for i in range(NUM_VARIABLES):
        circuit.measure(circuit.qubits[i], circuit.clbits[2-i])

def run_simulation(circuit):
    """Runs the simulation on the qasm_simulator
    
    Parameters
    ----------
    circuit: QuantumCircuit
        the circuit to simulate
    """
    
    backend = Aer.get_backend('qasm_simulator')
    job = backend.run(transpile(circuit, backend), shots=16384)
    result = job.result()
    counts = result.get_counts(circuit)
    return counts


def satisfies(clauses, possible_solution):
    """Check if an input satisfies a CNF
    
    Parameters
    ----------
    clauses: list
        the clauses defining the CNF
    possible_solution: str
        the input to check
        
    Returns
    -------
    bool
        True if the CNF is satisfied by possible_solution, False otherwise
    """
    
    individual_values = list(possible_solution)
    boolean_values = list(map(lambda elem: True if elem == '1' else False, individual_values))
    clauses_computed_values = []
    satisfied = True
    for clause in clauses:
        satisfied_clause = False
        for i in range(len(clause)):
            satisfied_clause = satisfied_clause or (boolean_values[i] if len(clause[i].split("not ")) == 1 else not(boolean_values[i]))
        if not satisfied_clause:
            return False
    return True
        


def general_3sat(show_circuit=False):

    input_cnf = input("Enter the 3SAT formula (CNF) [example: (x or y or not z) and (not x or y or z)]: ")

    (variables, clauses) = process(input_cnf)

    #  (¬x∨¬y∨¬z)∧(¬x∨¬y∨z)∧(¬x∨y∨z)∧(x∨¬y∨z)∧(x∨y∨¬z)∧(x∨y∨z)

    if check(variables, clauses) == 0:
        # 4 is arbitrary. Normally, if a solution is findable, it can be found in 3 or less iterations but 4 sometimes works too
        solutions = set()
        circuit = None
        for i in range(1, 4):
            circuit = prepare_circuit(variables, clauses)
            prepare_state_superposition(circuit)
            grover_circuit = build_grover(variables, clauses)
            for _ in range(1, i):
                circuit = circuit.compose(grover_circuit)
            measure_circuit(circuit)
            counts = run_simulation(circuit)
            max_count = max(counts, key=counts.get)
            if satisfies(clauses, max_count):
                solutions.add(max_count)
        if show_circuit:
            print(circuit)
        if len(solutions) == 0:
            print("No solutions found.")
        else:
            print(f"Possible solution(s): {solutions}") 

general_3sat(show_circuit=True)
