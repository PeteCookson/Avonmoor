(function () {
    const form = document.querySelector('[data-expense-form]');
    if (!form) return;

    const category = form.querySelector('[name="category"]');
    const employee = form.querySelector('[name="employee"]');
    const employeeField = form.querySelector('[data-field-name="employee"]');
    const businessUse = form.querySelector('[name="business_percentage"]');
    const businessUseField = form.querySelector('[data-field-name="business_percentage"]');
    if (!category) return;

    function updateEmployeeField() {
        if (employee && employeeField) {
            const isPayroll = category.value === 'payroll';
            employeeField.hidden = !isPayroll;
            employee.required = isPayroll;
            if (!isPayroll) employee.value = '';
        }

        if (businessUse && businessUseField) {
            const isFuel = category.value === 'fuel';
            businessUseField.hidden = !isFuel;
            businessUse.required = isFuel;
            if (!isFuel) businessUse.value = '';
        }
    }

    category.addEventListener('change', updateEmployeeField);
    updateEmployeeField();
})();
