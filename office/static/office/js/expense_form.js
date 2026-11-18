(function () {
    const form = document.querySelector('[data-expense-form]');
    if (!form) return;

    const category = form.querySelector('[name="category"]');
    const employee = form.querySelector('[name="employee"]');
    const employeeField = form.querySelector('[data-field-name="employee"]');
    if (!category) return;

    function updateEmployeeField() {
        if (employee && employeeField) {
            const isPayroll = category.value === 'payroll';
            employeeField.hidden = !isPayroll;
            employee.required = isPayroll;
            if (!isPayroll) employee.value = '';
        }

    }

    category.addEventListener('change', updateEmployeeField);
    updateEmployeeField();
})();
